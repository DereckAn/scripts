<#
.SYNOPSIS
  Starts a passive USBPcap capture of the Falchion Ace HFX config channel.

.DESCRIPTION
  PASSIVE ONLY. This script observes. It sends no keyboard command, writes no HID report
  and constructs no frame. Nothing here talks to the device.

  USBPcap is an *extcap* interface, not a native libpcap one. That means `dumpcap -D` will
  never list it -- you must use tshark, which spawns USBPcapCMD.exe for you. This script
  uses tshark throughout.

  Run elevated. Enumeration sometimes works unprivileged, but capturing does not.

  EVIDENCE RULES (log 131, finding 3). An existing -Out path is REFUSED. There is no
  -Force: the original first-launch capture was destroyed by an overwrite, and a switch
  that makes destroying evidence one keystroke away is the same hazard with a longer name.
  Use -Unique to get a timestamped filename instead. After tshark exits, the script checks
  tshark's own exit status, checks the file exists, is a regular file, is non-empty and
  starts with a pcap or pcapng magic number, and only then prints `saved:` with the size
  and SHA-256. A run that fails prints FAILED and removes the empty stub it would
  otherwise leave behind.

.EXAMPLE
  powershell -File capture.ps1 -List
  powershell -File capture.ps1 -Out ..\captures\03-profile-switch.pcapng
  powershell -File capture.ps1 -Out ..\captures\03-profile-switch.pcapng -Unique
#>
[CmdletBinding()]
param(
  [string]$Out,
  [string[]]$Interface,
  [int]$Seconds = 0,
  [switch]$List,
  [switch]$Unique          # append -yyyyMMdd-HHmmss so a run can never collide
)

$ErrorActionPreference = 'Stop'

# CANONICAL-BEGIN windows_tools.py owns these values
$FalchionVid = '0B05'
$FalchionPid = '1B7E'
$PcapMagics  = @('A1B2C3D4', 'D4C3B2A1', 'A1B23C4D', '4D3CB2A1', '0A0D0D0A')
# CANONICAL-END

function Test-CaptureMagic($path) {
  $head = [byte[]]::new(4)
  $fs = [IO.File]::OpenRead($path)
  try { $n = $fs.Read($head, 0, 4) } finally { $fs.Dispose() }
  if ($n -lt 4) { return $false }
  $be = ($head | ForEach-Object { '{0:X2}' -f $_ }) -join ''
  $le = (($head[3], $head[2], $head[1], $head[0]) | ForEach-Object { '{0:X2}' -f $_ }) -join ''
  return ($PcapMagics -contains $be) -or ($PcapMagics -contains $le)
}

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Host "NOT ELEVATED -- USBPcap capture will fail." -ForegroundColor Red
  Write-Host "Re-run from an Administrator PowerShell." -ForegroundColor Red
  exit 1
}

$tshark = 'C:\Program Files\Wireshark\tshark.exe'
if (-not (Test-Path -LiteralPath $tshark)) { throw "tshark not found at $tshark" }

# --- is the keyboard here? ---
$kb = Get-PnpDevice -PresentOnly |
      Where-Object { $_.InstanceId -like "USB\VID_$FalchionVid&PID_$FalchionPid*" } |
      Select-Object -First 1
if (-not $kb) {
  Write-Host "Keyboard $FalchionVid`:$FalchionPid not present." -ForegroundColor Red
  exit 1
}
Write-Host "keyboard : $($kb.InstanceId)" -ForegroundColor Cyan

$root = $null
$cur = $kb.InstanceId
for ($i = 0; $i -lt 12 -and $cur; $i++) {
  $p = (Get-PnpDeviceProperty -InstanceId $cur -KeyName 'DEVPKEY_Device_Parent' -ErrorAction SilentlyContinue).Data
  if (-not $p) { break }
  if ($p -match 'ROOT_HUB') { $root = $p; break }
  $cur = $p
}
if ($root) { Write-Host "root hub : $root" -ForegroundColor Cyan }

# --- enumerate USBPcap interfaces via tshark (NOT dumpcap: extcap is invisible to it) ---
$all = & $tshark -D
if ($LASTEXITCODE -ne 0) { throw "tshark -D exited $LASTEXITCODE" }
$cands = @($all | ForEach-Object { if ($_ -match '(\\\\\.\\USBPcap\d+)') { $Matches[1] } })

Write-Host "`nUSBPcap interfaces:" -ForegroundColor Cyan
if (-not $cands) {
  Write-Host "  (none)" -ForegroundColor Red
  Write-Host "  Check that C:\Program Files\Wireshark\extcap\USBPcapCMD.exe exists." -ForegroundColor Yellow
  exit 1
}
$cands | ForEach-Object { "   $_" }

if ($Interface) {
  # A name that is not on the enumerated list is an operator error, not a capture
  # that quietly records nothing.
  $bad = @($Interface | Where-Object { $cands -notcontains $_ })
  if ($bad) {
    Write-Host "`nNOT AN ENUMERATED INTERFACE: $($bad -join ', ')" -ForegroundColor Red
    Write-Host "Available: $($cands -join ', ')" -ForegroundColor Yellow
    exit 1
  }
} else {
  $Interface = $cands
  if ($cands.Count -eq 1) {
    Write-Host "`nusing $($cands[0])" -ForegroundColor Green
  } else {
    Write-Host "`n$($cands.Count) interfaces -- capturing ALL of them (no guessing needed)." -ForegroundColor Green
    Write-Host "decode.ps1 filters to the keyboard afterwards." -ForegroundColor DarkGray
  }
}

if ($List) { exit 0 }
if (-not $Out) { Write-Host "`n-Out <file.pcapng> is required to capture." -ForegroundColor Red; exit 1 }

if ($Unique) {
  $dirPart  = Split-Path $Out -Parent
  $basePart = [IO.Path]::GetFileNameWithoutExtension($Out)
  $extPart  = [IO.Path]::GetExtension($Out)
  $stamp    = Get-Date -Format 'yyyyMMdd-HHmmss'
  $leaf     = "$basePart-$stamp$extPart"
  $Out      = if ($dirPart) { Join-Path $dirPart $leaf } else { $leaf }
}

# Refuse a collision BEFORE tshark is launched, so a mistake costs a message
# and not a capture. There is deliberately no override switch.
if (Test-Path -LiteralPath $Out) {
  Write-Host "`nREFUSING: $Out already exists." -ForegroundColor Red
  Write-Host "Captures are evidence and this script will not overwrite one." -ForegroundColor Red
  Write-Host "Choose another name, or re-run with -Unique." -ForegroundColor Yellow
  exit 1
}

$dir = Split-Path $Out -Parent
if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }

$a = @()
foreach ($i in @($Interface)) { $a += @('-i', $i) }
$a += @('-w', $Out)
if ($Seconds -gt 0) { $a += @('-a', "duration:$Seconds") }

Write-Host "`ncapturing on $(@($Interface) -join ', ')" -ForegroundColor Green
Write-Host "  -> $Out" -ForegroundColor Green
Write-Host "Ctrl+C to stop.`n" -ForegroundColor Green

& $tshark @a
$code = $LASTEXITCODE

function Fail($why) {
  Write-Host "`nFAILED: $why" -ForegroundColor Red
  if ((Test-Path -LiteralPath $Out) -and ((Get-Item -LiteralPath $Out).Length -eq 0)) {
    Remove-Item -LiteralPath $Out -Force
    Write-Host "removed the empty stub $Out" -ForegroundColor Yellow
  } elseif (Test-Path -LiteralPath $Out) {
    Write-Host "left in place for inspection: $Out" -ForegroundColor Yellow
  }
  exit 1
}

if ($code -ne 0)                        { Fail "tshark exited $code" }
if (-not (Test-Path -LiteralPath $Out -PathType Leaf)) { Fail "no output file at $Out" }
$item = Get-Item -LiteralPath $Out
if ($item.Length -eq 0)                 { Fail "output is zero bytes" }
if (-not (Test-CaptureMagic $Out))      { Fail "output does not start with a pcap or pcapng magic number" }

$hash = (Get-FileHash -LiteralPath $Out -Algorithm SHA256).Hash.ToLower()
Write-Host "`nsaved: $Out" -ForegroundColor Green
Write-Host ("  bytes : {0}" -f $item.Length) -ForegroundColor Green
Write-Host ("  sha256: {0}" -f $hash) -ForegroundColor Green
