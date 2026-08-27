<#
.SYNOPSIS
  Starts a USBPcap capture of the Falchion Ace HFX config channel.

.DESCRIPTION
  Finds which USBPcap root-hub interface the keyboard is on and runs dumpcap against it.
  MUST be elevated -- USBPcap interfaces are invisible to non-admin processes, which is the
  single most common "Wireshark shows nothing" cause.

.EXAMPLE
  # list interfaces and which one the keyboard is on
  powershell -ExecutionPolicy Bypass -File capture.ps1 -List

  # capture until Ctrl+C
  powershell -ExecutionPolicy Bypass -File capture.ps1 -Out ..\captures\01-ac-first-launch.pcapng
#>
[CmdletBinding()]
param(
  [string]$Out,
  [string]$Interface,
  [int]$Seconds = 0,
  [switch]$List
)

$ErrorActionPreference = 'Stop'
$VID = '0B05'; $PID_ = '1B7E'

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Host "NOT ELEVATED -- USBPcap interfaces will not be listed." -ForegroundColor Red
  Write-Host "Re-run from an Administrator PowerShell." -ForegroundColor Red
  exit 1
}

$dumpcap = 'C:\Program Files\Wireshark\dumpcap.exe'
if (-not (Test-Path $dumpcap)) { throw "dumpcap not found at $dumpcap" }

# --- which root hub is the keyboard under? ---
$kb = Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like "USB\VID_$VID&PID_$PID_*" } | Select-Object -First 1
if (-not $kb) { Write-Host "Keyboard $VID`:$PID_ not present." -ForegroundColor Red; exit 1 }

$hubPath = @()
$cur = $kb.InstanceId
for ($i = 0; $i -lt 12 -and $cur; $i++) {
  $p = (Get-PnpDeviceProperty -InstanceId $cur -KeyName 'DEVPKEY_Device_Parent' -ErrorAction SilentlyContinue).Data
  if (-not $p) { break }
  $hubPath += $p
  $cur = $p
}

Write-Host "keyboard : $($kb.InstanceId)" -ForegroundColor Cyan
Write-Host "hub chain:" -ForegroundColor Cyan
$hubPath | ForEach-Object { "   $_" }

# --- enumerate USBPcap interfaces ---
$ifaces = & $dumpcap -D 2>$null | Where-Object { $_ -match 'USBPcap' }
Write-Host "`nUSBPcap interfaces:" -ForegroundColor Cyan
if (-not $ifaces) {
  Write-Host "  (none) -- USBPcap driver not loaded, or a reboot is still pending." -ForegroundColor Red
  exit 1
}
$ifaces | ForEach-Object { "   $_" }

if (-not $Interface) {
  # USBPcapN maps to root hub N; match by the ROOT_HUB entry in the chain
  $root = $hubPath | Where-Object { $_ -match 'ROOT_HUB' } | Select-Object -First 1
  if ($root -and $root -match 'ROOT_HUB\w*\\(\d+)') { }
  $cands = @($ifaces | ForEach-Object { if ($_ -match '(\\\\\.\\USBPcap\d+)') { $Matches[1] } })
  if ($cands.Count -eq 1) {
    $Interface = $cands[0]
    Write-Host "`nOnly one interface present; using $Interface" -ForegroundColor Green
  } else {
    Write-Host "`nMultiple USBPcap interfaces. Determine the right one empirically:" -ForegroundColor Yellow
    Write-Host "  start a short capture on each, unplug/replug the keyboard, and see which" -ForegroundColor Yellow
    Write-Host "  one records the enumeration burst. Then pass -Interface \\.\USBPcapN" -ForegroundColor Yellow
    if ($List) { exit 0 }
    exit 1
  }
}

if ($List) { exit 0 }
if (-not $Out) { Write-Host "`n-Out <file.pcapng> is required to capture." -ForegroundColor Red; exit 1 }

$dir = Split-Path $Out -Parent
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }

$args = @('-i', $Interface, '-w', $Out)
if ($Seconds -gt 0) { $args += @('-a', "duration:$Seconds") }

Write-Host "`ncapturing on $Interface -> $Out" -ForegroundColor Green
Write-Host "Ctrl+C to stop.`n" -ForegroundColor Green
& $dumpcap @args
Write-Host "`nsaved: $Out" -ForegroundColor Green
