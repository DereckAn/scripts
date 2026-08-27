<#
.SYNOPSIS
  Starts a USBPcap capture of the Falchion Ace HFX config channel.

.DESCRIPTION
  USBPcap is an *extcap* interface, not a native libpcap one. That means `dumpcap -D` will
  never list it -- you must use tshark, which spawns USBPcapCMD.exe for you. This script
  uses tshark throughout.

  Run elevated. Enumeration sometimes works unprivileged, but capturing does not.

.EXAMPLE
  powershell -File capture.ps1 -List
  powershell -File capture.ps1 -Out ..\captures\01-first-launch.pcapng
#>
[CmdletBinding()]
param(
  [string]$Out,
  [string[]]$Interface,
  [int]$Seconds = 0,
  [switch]$List
)

$ErrorActionPreference = 'Stop'
$VID = '0B05'; $PID_ = '1B7E'

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Host "NOT ELEVATED -- USBPcap capture will fail." -ForegroundColor Red
  Write-Host "Re-run from an Administrator PowerShell." -ForegroundColor Red
  exit 1
}

$tshark = 'C:\Program Files\Wireshark\tshark.exe'
if (-not (Test-Path $tshark)) { throw "tshark not found at $tshark" }

# --- is the keyboard here? ---
$kb = Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like "USB\VID_$VID&PID_$PID_*" } | Select-Object -First 1
if (-not $kb) { Write-Host "Keyboard $VID`:$PID_ not present." -ForegroundColor Red; exit 1 }
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
$all = & $tshark -D 2>$null
$cands = @($all | ForEach-Object { if ($_ -match '(\\\\\.\\USBPcap\d+)') { $Matches[1] } })

Write-Host "`nUSBPcap interfaces:" -ForegroundColor Cyan
if (-not $cands) {
  Write-Host "  (none)" -ForegroundColor Red
  Write-Host "  Check that C:\Program Files\Wireshark\extcap\USBPcapCMD.exe exists." -ForegroundColor Yellow
  exit 1
}
$cands | ForEach-Object { "   $_" }

if (-not $Interface) {
  if ($cands.Count -eq 1) {
    $Interface = $cands
    Write-Host "`nusing $($cands[0])" -ForegroundColor Green
  } else {
    Write-Host "`n$($cands.Count) interfaces -- capturing ALL of them (no guessing needed)." -ForegroundColor Green
    Write-Host "decode.ps1 filters to the keyboard afterwards." -ForegroundColor DarkGray
    $Interface = $cands
  }
}

if ($List) { exit 0 }
if (-not $Out) { Write-Host "`n-Out <file.pcapng> is required to capture." -ForegroundColor Red; exit 1 }

$dir = Split-Path $Out -Parent
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }

$a = @()
foreach ($i in @($Interface)) { $a += @('-i', $i) }
$a += @('-w', $Out)
if ($Seconds -gt 0) { $a += @('-a', "duration:$Seconds") }

Write-Host "`ncapturing on $(@($Interface) -join ', ')" -ForegroundColor Green
Write-Host "  -> $Out" -ForegroundColor Green
Write-Host "Ctrl+C to stop.`n" -ForegroundColor Green
& $tshark @a
Write-Host "`nsaved: $Out" -ForegroundColor Green
