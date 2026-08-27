<#
.SYNOPSIS
  Extracts and annotates Falchion HID reports from a USBPcap capture.

.DESCRIPTION
  Pulls usb.capdata out of a .pcapng with tshark, keeps only the 0b05:1b7e traffic, and
  prints one line per 64-byte report with direction, so opcodes are obvious at a glance.

  -Diff compares two captures and shows only reports unique to each, which is how you
  isolate "what changed when I changed one setting".

.EXAMPLE
  .\decode.ps1 -Path ..\captures\remap-f1-a.pcapng
  .\decode.ps1 -Path ..\captures\remap-f1-b.pcapng -Diff ..\captures\remap-f1-a.pcapng
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$Path,
  [string]$Diff,
  [switch]$IncludeIdle,      # keep repeated/keepalive reports
  [string]$Csv
)

$ErrorActionPreference = 'Stop'
$tshark = 'C:\Program Files\Wireshark\tshark.exe'
if (-not (Test-Path $tshark)) { throw "tshark not found at $tshark" }

function Get-Reports($pcap) {
  if (-not (Test-Path $pcap)) { throw "not found: $pcap" }
  $raw = & $tshark -r $pcap -Y 'usb.capdata' -T fields `
                   -e frame.number -e frame.time_relative -e usb.src -e usb.dst -e usb.capdata 2>$null
  $out = foreach ($l in $raw) {
    if (-not $l) { continue }
    $f = $l -split "`t"
    if ($f.Count -lt 5 -or -not $f[4]) { continue }
    $hex = ($f[4] -replace '[^0-9a-fA-F]', '').ToUpper()
    if ($hex.Length -lt 4) { continue }
    $dir = if ($f[2] -match 'host') { 'OUT' } elseif ($f[3] -match 'host') { 'IN ' } else { '?  ' }
    [pscustomobject]@{
      Frame = [int]$f[0]
      Time  = [double]$f[1]
      Dir   = $dir
      Len   = $hex.Length / 2
      Op    = $hex.Substring(0, [Math]::Min(6, $hex.Length))
      Hex   = $hex
    }
  }
  ,@($out)
}

function Format-Report($r) {
  $bytes = ($r.Hex -split '(..)' | Where-Object { $_ })
  $head = ($bytes | Select-Object -First 16) -join ' '
  $tail = ($bytes | Select-Object -Skip 16) -join ''
  $nz = if ($tail -match '^0*$') { '(rest zero)' } else { '(rest nonzero)' }
  "{0,6}  {1,8:F3}  {2}  {3,3}B  {4}  {5}" -f $r.Frame, $r.Time, $r.Dir, $r.Len, $head, $nz
}

$a = Get-Reports $Path
Write-Host "$Path : $($a.Count) HID reports" -ForegroundColor Cyan

if ($Csv) { $a | Export-Csv $Csv -NoTypeInformation; Write-Host "csv -> $Csv" -ForegroundColor Green }

if (-not $Diff) {
  $show = $a
  if (-not $IncludeIdle) {
    # collapse runs of identical payloads (polling / keepalive noise)
    $seen = @{}
    $show = $a | Where-Object { $k = "$($_.Dir)$($_.Hex)"; if ($seen.ContainsKey($k)) { $false } else { $seen[$k] = 1; $true } }
    Write-Host "unique payloads: $($show.Count)  (use -IncludeIdle for all)" -ForegroundColor DarkGray
  }
  Write-Host "`n frame      time  dir  len  first 16 bytes" -ForegroundColor DarkGray
  $show | ForEach-Object { Format-Report $_ }

  Write-Host "`nopcode histogram (first 3 bytes, OUT only):" -ForegroundColor Cyan
  $a | Where-Object { $_.Dir -eq 'OUT' } | Group-Object Op | Sort-Object Count -Descending |
    ForEach-Object { "  {0}  x{1}" -f $_.Name, $_.Count }
  exit 0
}

$b = Get-Reports $Diff
Write-Host "$Diff : $($b.Count) HID reports" -ForegroundColor Cyan
$setB = @{}; $b | ForEach-Object { $setB["$($_.Dir)$($_.Hex)"] = 1 }
$setA = @{}; $a | ForEach-Object { $setA["$($_.Dir)$($_.Hex)"] = 1 }

Write-Host "`nONLY in $(Split-Path $Path -Leaf):" -ForegroundColor Yellow
$a | Where-Object { -not $setB.ContainsKey("$($_.Dir)$($_.Hex)") } |
    Group-Object Hex | ForEach-Object { Format-Report $_.Group[0] }

Write-Host "`nONLY in $(Split-Path $Diff -Leaf):" -ForegroundColor Yellow
$b | Where-Object { -not $setA.ContainsKey("$($_.Dir)$($_.Hex)") } |
    Group-Object Hex | ForEach-Object { Format-Report $_.Group[0] }
