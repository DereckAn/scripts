<#
.SYNOPSIS
  Captures ASUS AacKbHal debug output live (OutputDebugString / DBWIN).

.DESCRIPTION
  AacKbHal_x64.dll logs every HAL call as "[<Class>][<Method>] ..." via OutputDebugString.
  Nothing writes those to a file, but any process can listen on the global DBWIN buffer.

  Run this while you click around in Armoury Crate and you get a timestamped list of exactly
  which HAL methods fired -- which lets you label the packets in a simultaneous USBPcap
  capture without guessing.

  MUST run elevated (Global\ objects + reading output from the session-0 AC service).
  Only ONE DBWIN listener can exist at a time -- close DebugView/Sysinternals first.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File haltrace.ps1 -Out haltrace.log
  powershell -ExecutionPolicy Bypass -File haltrace.ps1 -Out haltrace.log -FilterAsus
#>
[CmdletBinding()]
param(
  [string]$Out = "haltrace.log",
  [switch]$FilterAsus,      # only keep lines that look like ASUS HAL logs
  [int]$Seconds = 0         # 0 = run until Ctrl+C
)

$ErrorActionPreference = 'Stop'

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Warning "Not elevated. You will likely see nothing from the Armoury Crate service."
  Write-Warning "Re-run from an Administrator PowerShell."
}

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class Dbwin {
  [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
  public static extern IntPtr CreateFileMappingW(IntPtr h, IntPtr sa, uint prot, uint hi, uint lo, string name);
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern IntPtr MapViewOfFile(IntPtr h, uint access, uint hi, uint lo, UIntPtr n);
  [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
  public static extern IntPtr CreateEventW(IntPtr sa, bool manual, bool initial, string name);
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern uint WaitForSingleObject(IntPtr h, uint ms);
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool SetEvent(IntPtr h);
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool UnmapViewOfFile(IntPtr p);
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool CloseHandle(IntPtr h);
}
'@

$PAGE_READWRITE = 0x04
$FILE_MAP_READ  = 0x0004
$INVALID        = [IntPtr]::Zero

# Try Global\ first (reaches session 0 services), fall back to local.
$prefixes = @('Global\', '')
$map = $INVALID; $prefix = $null
foreach ($p in $prefixes) {
  $m = [Dbwin]::CreateFileMappingW([IntPtr](-1), $INVALID, $PAGE_READWRITE, 0, 4096, "$($p)DBWIN_BUFFER")
  if ($m -ne $INVALID) { $map = $m; $prefix = $p; break }
}
if ($map -eq $INVALID) { throw "Could not create DBWIN_BUFFER. Another listener (DebugView?) is probably running." }

$bufReady  = [Dbwin]::CreateEventW($INVALID, $false, $true,  "$($prefix)DBWIN_BUFFER_READY")
$dataReady = [Dbwin]::CreateEventW($INVALID, $false, $false, "$($prefix)DBWIN_DATA_READY")
$view      = [Dbwin]::MapViewOfFile($map, $FILE_MAP_READ, 0, 0, [UIntPtr]::new(4096))
if ($view -eq $INVALID) { throw "MapViewOfFile failed" }

Write-Host "Listening on $($prefix)DBWIN_BUFFER  ->  $Out" -ForegroundColor Green
Write-Host "Now drive Armoury Crate. Ctrl+C to stop.`n" -ForegroundColor Green

$sw = [Diagnostics.Stopwatch]::StartNew()
$n  = 0
try {
  [void][Dbwin]::SetEvent($bufReady)
  while ($true) {
    if ($Seconds -gt 0 -and $sw.Elapsed.TotalSeconds -ge $Seconds) { break }
    $w = [Dbwin]::WaitForSingleObject($dataReady, 500)
    if ($w -ne 0) { continue }   # timeout -> loop so Ctrl+C stays responsive

    $pid_ = [Runtime.InteropServices.Marshal]::ReadInt32($view, 0)
    $str  = [Runtime.InteropServices.Marshal]::PtrToStringAnsi([IntPtr]::Add($view, 4))
    [void][Dbwin]::SetEvent($bufReady)

    if ($null -eq $str) { continue }
    $str = $str.TrimEnd("`r", "`n")
    if ($FilterAsus -and $str -notmatch '^\s*\[(Aac|Kb)') { continue }

    $line = "{0:HH:mm:ss.fff}  pid={1,-6} {2}" -f (Get-Date), $pid_, $str
    $line | Tee-Object -FilePath $Out -Append
    $n++
  }
}
finally {
  [void][Dbwin]::UnmapViewOfFile($view)
  [void][Dbwin]::CloseHandle($map)
  [void][Dbwin]::CloseHandle($bufReady)
  [void][Dbwin]::CloseHandle($dataReady)
  Write-Host "`nCaptured $n lines -> $Out" -ForegroundColor Green
}
