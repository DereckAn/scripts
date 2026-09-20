<#
.SYNOPSIS
  Extracts and annotates the Falchion's 64-byte vendor-HID reports from a USBPcap capture.

.DESCRIPTION
  Payloads come from usbhid.data. usb.capdata is EMPTY for USBPcap captures dissected by
  Wireshark 4.6/4.7 -- the previous version of this script read usb.capdata and therefore
  decoded nothing at all from the preserved captures (log 131, finding 2).

  The subject is found dynamically: every device that identifies itself on the wire is read
  out of the capture, and only the one whose VID:PID is 0b05:1b7e is decoded. Identity is
  keyed by (capture interface, USB bus, device address), because a device address is scoped
  to a bus -- 01-first-launch.pcapng holds address 1 twice, an ASMedia hub on bus 2 and a
  Logitech receiver on bus 3. A device that re-enumerates mid-capture holds more than one
  key and ALL of them are used, so nothing is hard-coded to bus 2 or to address 2, 6 or 7.
  Descriptor identity is (idVendor, idProduct, bcdDevice). One interface/bus/address key
  that reports two different such tuples is a DESCRIPTOR-IDENTITY CONFLICT and the script
  refuses the capture rather than guessing. It cannot detect an address reused by a device
  with an IDENTICAL descriptor -- two units of the same model and firmware are
  indistinguishable here, and that remains an unvalidated limitation.
  Traffic from other devices on the same or another root hub is never decoded.

  Only the vendor configuration pair is kept: OUT endpoint 0x0d, IN endpoint 0x85, payload
  exactly 64 bytes. Direction comes from the endpoint's direction bit, not from matching the
  word "host" in usb.src/usb.dst.

  -Diff compares two captures and shows only reports unique to each, which is how you
  isolate "what changed when I changed one setting". Direction is part of a report's
  identity, so an IN echo is never collapsed into the OUT request it echoes.

  Read-only with respect to both the keyboard and the capture files.

  The offline twin of this script is tool/decode_capture.py, which the unit suite runs
  against captures/02-polling-rate.pcap. `python3 tool/decode_capture.py --check` fails if
  the constants below stop matching it.

.EXAMPLE
  .\decode.ps1 -Path ..\captures\02-polling-rate.pcap
  .\decode.ps1 -Path ..\captures\remap-f1-b.pcapng -Diff ..\captures\remap-f1-a.pcapng
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$Path,
  [string]$Diff,
  [switch]$IncludeIdle,      # keep every report, not just the first of each payload
  [string]$Csv
)

$ErrorActionPreference = 'Stop'

# CANONICAL-BEGIN decode_capture.py owns these values
$FalchionVid       = 0x0B05
$FalchionPid       = 0x1B7E
$VendorOutEndpoint = 0x0D
$VendorInEndpoint  = 0x85
$ReportBytes       = 64
# CANONICAL-END

$tshark = 'C:\Program Files\Wireshark\tshark.exe'
if (-not (Test-Path -LiteralPath $tshark)) { throw "tshark not found at $tshark" }

function Invoke-Tshark($pcap, $displayFilter, $fields) {
  $a = @('-r', $pcap, '-T', 'fields', '-E', 'separator=/t')
  if ($displayFilter) { $a += @('-Y', $displayFilter) }
  foreach ($f in $fields) { $a += @('-e', $f) }
  $out = & $tshark @a
  if ($LASTEXITCODE -ne 0) { throw "tshark exited $LASTEXITCODE on $pcap" }
  ,@($out)
}

function Get-SubjectKey($pcap) {
  # A USB device address is scoped to a BUS, and capture.ps1 records every
  # USBPcap interface into one file. 01-first-launch.pcapng holds address 1
  # twice: an ASMedia hub on bus 2 and a Logitech receiver on bus 3. So the
  # identity is (capture interface, bus, address), never the address alone.
  # A capture spanning a replug holds the subject under two keys; both count.
  $rows = Invoke-Tshark $pcap 'usb.idVendor' @(
    'frame.interface_id', 'usb.bus_id', 'usb.device_address',
    'usb.idVendor', 'usb.idProduct', 'usb.bcdDevice')
  $seen = @{}          # key -> set of "vid:pid:bcd" observed for it
  foreach ($l in $rows) {
    if (-not $l) { continue }
    $f = $l -split "`t"
    if ($f.Count -lt 6 -or -not $f[2]) { continue }
    $key = "$($f[0].Trim())|$($f[1].Trim())|$([int]$f[2])"
    # Descriptor identity is VID, PID and bcdDevice -- the same three fields
    # tool/decode_capture.py uses. Dropping bcdDevice here would make the two
    # implementations disagree about what counts as a conflict.
    $ident = "$($f[3]):$($f[4]):$($f[5])"
    if (-not $seen.ContainsKey($key)) { $seen[$key] = @{} }
    $seen[$key][$ident] = 1
  }
  # DESCRIPTOR-IDENTITY CONFLICT, named for what it measures. One key that
  # reported two different VID:PID:bcdDevice tuples cannot be separated by a
  # display filter, so refuse rather than silently take the last owner. This
  # does NOT detect an address reused by a device with an IDENTICAL
  # descriptor; nothing here can.
  $conflicting = @($seen.Keys | Where-Object { $seen[$_].Count -gt 1 })
  if ($conflicting) {
    throw ("{0}: descriptor-identity conflict on these interface/bus/address keys -- " +
           "more than one VID:PID:bcdDevice each, so nothing may be attributed to " +
           "either owner: {1}") -f $pcap, ($conflicting -join ', ')
  }
  $keys = @($seen.Keys | Where-Object {
      $ident = @($seen[$_].Keys)[0] -split ':'
      ([Convert]::ToInt32($ident[0], 16) -eq $FalchionVid) -and
      ([Convert]::ToInt32($ident[1], 16) -eq $FalchionPid)
    } | Sort-Object)   # bcdDevice is part of the conflict test, not of selection
  if ($keys.Count -eq 0) {
    throw ("{0}: no device identified itself as {1:x4}:{2:x4}; this capture has no " +
           "subject and nothing in it may be attributed to the keyboard") -f
          $pcap, $FalchionVid, $FalchionPid
  }
  ,$keys
}

function Get-KeyFilter($key) {
  $p = $key -split '\|'
  $parts = @()
  if ($p[0]) { $parts += "frame.interface_id==$($p[0])" }
  if ($p[1]) { $parts += "usb.bus_id==$($p[1])" }
  $parts += "usb.device_address==$($p[2])"
  '(' + ($parts -join ' && ') + ')'
}

function Get-ReportFilter($keys) {
  $scoped = ($keys | ForEach-Object { Get-KeyFilter $_ }) -join ' || '
  ('({0}) && (usb.endpoint_address==0x{1:x2} || usb.endpoint_address==0x{2:x2}) && ' +
   'usb.data_len=={3}') -f $scoped, $VendorOutEndpoint, $VendorInEndpoint, $ReportBytes
}

function Get-Reports($pcap) {
  if (-not (Test-Path -LiteralPath $pcap)) { throw "not found: $pcap" }
  $keys   = Get-SubjectKey $pcap
  $filter = Get-ReportFilter $keys
  Write-Host ("{0}`n  subject at {1}`n  filter {2}" -f
              $pcap, ($keys -join '; '), $filter) -ForegroundColor Cyan

  $rows = Invoke-Tshark $pcap $filter @(
    'frame.number', 'frame.time_relative', 'frame.time_epoch',
    'frame.interface_id', 'usb.bus_id', 'usb.device_address',
    'usb.endpoint_address', 'usb.data_len', 'usbhid.data')
  $wanted = @{}; foreach ($k in $keys) { $wanted[$k] = 1 }
  $out = foreach ($l in $rows) {
    if (-not $l) { continue }
    $f = $l -split "`t"
    if ($f.Count -lt 9 -or -not $f[8]) { continue }   # URB with no payload
    # Re-check the scope on every row: a filter is a request, not a guarantee.
    $key = "$($f[3].Trim())|$($f[4].Trim())|$([int]$f[5])"
    if (-not $wanted.ContainsKey($key)) { continue }
    $hex = ($f[8] -replace '[^0-9a-fA-F]', '').ToUpper()
    if ($hex.Length -ne ($ReportBytes * 2)) {
      throw "$pcap frame $($f[0]): usbhid.data is $($hex.Length / 2) bytes, not $ReportBytes"
    }
    $ep = [Convert]::ToInt32($f[6], 16)
    if (($ep -ne $VendorOutEndpoint) -and ($ep -ne $VendorInEndpoint)) {
      throw "$pcap frame $($f[0]): endpoint $($f[6]) passed the filter but is not a vendor endpoint"
    }
    [pscustomobject]@{
      Frame = [int]$f[0]
      Time  = [double]$f[1]
      Epoch = [double]$f[2]      # absolute, for correlating with haltrace.log
      Key   = $key
      Addr  = [int]$f[5]
      Ep    = $ep
      # Direction from bit 7 of the endpoint address. No text matching.
      Dir   = if ($ep -band 0x80) { 'IN ' } else { 'OUT' }
      Len   = $hex.Length / 2
      Op    = $hex.Substring(0, 4)
      Hex   = $hex
    }
  }
  $out = @($out)
  if ($out.Count -eq 0) {
    throw ("{0}: the subject is present but sent no {1}-byte report on endpoint " +
           "0x{2:x2} or 0x{3:x2}; there is nothing to decode") -f
          $pcap, $ReportBytes, $VendorOutEndpoint, $VendorInEndpoint
  }
  ,$out
}

# Direction is part of a report's identity: the device echoes an OUT request
# verbatim on the IN endpoint, so keying on the payload alone would merge a
# request with its own reply and hide a whole transaction from -Diff.
function Get-Key($r) { "$($r.Dir)|$($r.Hex)" }

function Format-Report($r) {
  $bytes = ($r.Hex -split '(..)' | Where-Object { $_ })
  $head = ($bytes | Select-Object -First 16) -join ' '
  $tail = ($bytes | Select-Object -Skip 16) -join ''
  $nz = if ($tail -match '^0*$') { '(rest zero)' } else { '(rest nonzero)' }
  "{0,6}  {1,9:F3}  {2}  {3,3}B  {4}  {5}" -f $r.Frame, $r.Time, $r.Dir, $r.Len, $head, $nz
}

function Select-Unique($records) {
  $seen = @{}
  ,@($records | Where-Object {
      $k = Get-Key $_
      if ($seen.ContainsKey($k)) { $false } else { $seen[$k] = 1; $true } })
}

$a = Get-Reports $Path
Write-Host ("  {0} reports: {1} OUT, {2} IN" -f $a.Count,
            @($a | Where-Object { $_.Dir -eq 'OUT' }).Count,
            @($a | Where-Object { $_.Dir -eq 'IN ' }).Count) -ForegroundColor Cyan

if ($Csv) { $a | Export-Csv $Csv -NoTypeInformation; Write-Host "csv -> $Csv" -ForegroundColor Green }

if (-not $Diff) {
  $show = if ($IncludeIdle) { $a } else { Select-Unique $a }
  if (-not $IncludeIdle) {
    Write-Host "unique payloads: $($show.Count)  (use -IncludeIdle for all)" -ForegroundColor DarkGray
  }
  Write-Host "`n frame       time  dir  len  first 16 bytes" -ForegroundColor DarkGray
  $show | ForEach-Object { Format-Report $_ }

  Write-Host "`nOUT opcode histogram (first two bytes):" -ForegroundColor Cyan
  $a | Where-Object { $_.Dir -eq 'OUT' } | Group-Object Op | Sort-Object Name |
    ForEach-Object { "  {0} {1}  x{2}" -f $_.Name.Substring(0,2), $_.Name.Substring(2,2), $_.Count }
  exit 0
}

$b = Get-Reports $Diff
Write-Host "  $($b.Count) reports in the baseline" -ForegroundColor Cyan

$setB = @{}; $b | ForEach-Object { $setB[(Get-Key $_)] = 1 }
$setA = @{}; $a | ForEach-Object { $setA[(Get-Key $_)] = 1 }

Write-Host "`nONLY in $(Split-Path $Path -Leaf):" -ForegroundColor Yellow
Select-Unique $a | Where-Object { -not $setB.ContainsKey((Get-Key $_)) } |
    ForEach-Object { Format-Report $_ }

Write-Host "`nONLY in $(Split-Path $Diff -Leaf):" -ForegroundColor Yellow
Select-Unique $b | Where-Object { -not $setA.ContainsKey((Get-Key $_)) } |
    ForEach-Object { Format-Report $_ }
