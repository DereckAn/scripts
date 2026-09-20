<#
.SYNOPSIS
  Captures ASUS AacKbHal debug output live (OutputDebugString / DBWIN).

.DESCRIPTION
  AacKbHal_x64.dll logs every HAL call as "[<Class>][<Method>] ..." via OutputDebugString.
  Nothing writes those to a file, but one process at a time can own the global DBWIN
  buffer. Run this while you click around in Armoury Crate and you get a timestamped list
  of exactly which HAL methods fired, which lets you label the packets in a simultaneous
  USBPcap capture without guessing.

  PASSIVE ONLY. It reads a shared-memory ring buffer. It sends nothing to the keyboard.

  SESSION INTEGRITY (log 131, finding 5):

  * An existing -Out path is REFUSED. Appending a second experiment to a first one
    produces a trace nobody can attribute, which is worse than no trace. Use -Unique.
  * Elevation is REQUIRED, not warned about. Without it the Global\ objects are out of
    reach and the Armoury Crate service's output -- the only output worth having -- is
    invisible. A run that would silently capture nothing exits instead.
  * CreateFileMapping SUCCEEDS when the object already exists and reports it only through
    GetLastError == ERROR_ALREADY_EXISTS (183). That is checked. If DebugView or another
    listener already owns DBWIN, this script refuses rather than racing it for messages;
    two listeners split the stream and neither one gets a complete trace.
  * Every handle is released on a partial initialisation failure, not just on the happy
    path.
  * At completion the line count, the output size and its SHA-256 are printed.

  A ZERO-EVENT RUN STILL PRODUCES AN ARTIFACT. The output file is created and its header
  written before listening starts, so a session in which nothing logs -- which is the
  EXPECTED result of the Armoury-Crate-closed experiment -- still yields a file with a
  start time, a clock reference, an end time, a line count of zero and a SHA-256. A step
  that requires a HAL artifact therefore never fails merely because no producer was
  running.

  CLOCKS. Every line is stamped from the WINDOWS WALL CLOCK, in UTC and in local time, and
  the header records both at session start. USBPcap frames are stamped by the capture
  engine. The two are NOT the same clock and are not automatically aligned: correlate on
  absolute time (the header UTC here against `frame.time_epoch` / `frame.time` from the
  capture, which decode.ps1 now carries), and treat the alignment as approximate and
  manual. `frame.time_relative` alone cannot be correlated with this file at all.

  KNOWN LIMITATION, stated rather than papered over: even as the sole listener, this sees
  only what OutputDebugString delivers while it is running. Messages emitted before the
  listener starts, or while it is between Wait calls, are lost -- DBWIN has one slot and
  no queue. A missing line is therefore not evidence that a HAL call did not happen.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File haltrace.ps1 -Out ..\captures\03-haltrace.log
  powershell -ExecutionPolicy Bypass -File haltrace.ps1 -Out trace.log -Unique -FilterAsus
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$Out,
  [switch]$FilterAsus,      # only keep lines that look like ASUS HAL logs
  [switch]$Unique,          # append -yyyyMMdd-HHmmss so a run can never collide
  [int]$Seconds = 0         # 0 = run until Ctrl+C
)

$ErrorActionPreference = 'Stop'

if ($Unique) {
  $dirPart  = Split-Path $Out -Parent
  $basePart = [IO.Path]::GetFileNameWithoutExtension($Out)
  $extPart  = [IO.Path]::GetExtension($Out)
  $stamp    = Get-Date -Format 'yyyyMMdd-HHmmss'
  $leaf     = "$basePart-$stamp$extPart"
  $Out      = if ($dirPart) { Join-Path $dirPart $leaf } else { $leaf }
}

if (Test-Path -LiteralPath $Out) {
  Write-Host "REFUSING: $Out already exists." -ForegroundColor Red
  Write-Host "A trace file holds one experiment. Appending a second makes both" -ForegroundColor Red
  Write-Host "unattributable. Choose another name, or re-run with -Unique." -ForegroundColor Yellow
  exit 1
}

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Host "NOT ELEVATED -- the Global\ DBWIN objects are unreachable and the" -ForegroundColor Red
  Write-Host "Armoury Crate service's output would not be captured at all." -ForegroundColor Red
  Write-Host "Re-run from an Administrator PowerShell." -ForegroundColor Red
  exit 1
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

$PAGE_READWRITE       = 0x04
$FILE_MAP_READ        = 0x0004
$ERROR_ALREADY_EXISTS = 183
$INVALID              = [IntPtr]::Zero

$map = $INVALID; $bufReady = $INVALID; $dataReady = $INVALID; $view = $INVALID

function Close-All {
  if ($script:view      -ne $INVALID) { [void][Dbwin]::UnmapViewOfFile($script:view) }
  if ($script:map       -ne $INVALID) { [void][Dbwin]::CloseHandle($script:map) }
  if ($script:bufReady  -ne $INVALID) { [void][Dbwin]::CloseHandle($script:bufReady) }
  if ($script:dataReady -ne $INVALID) { [void][Dbwin]::CloseHandle($script:dataReady) }
  $script:view = $INVALID; $script:map = $INVALID
  $script:bufReady = $INVALID; $script:dataReady = $INVALID
}

function Abort($why) {
  Close-All
  Write-Host "FAILED: $why" -ForegroundColor Red
  exit 1
}

# Global\ only. A local fallback would "succeed" while capturing none of the
# session-0 service output this tool exists to read.
$prefix = 'Global\'

$map = [Dbwin]::CreateFileMappingW([IntPtr](-1), $INVALID, $PAGE_READWRITE, 0, 4096,
                                   "${prefix}DBWIN_BUFFER")
$err = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
if ($map -eq $INVALID) { Abort "CreateFileMapping(${prefix}DBWIN_BUFFER) failed, error $err" }
if ($err -eq $ERROR_ALREADY_EXISTS) {
  Abort ("${prefix}DBWIN_BUFFER already exists -- another listener (DebugView?) owns it. " +
         "Two listeners split the message stream and neither gets a complete trace. " +
         "Close the other one and re-run.")
}

$bufReady = [Dbwin]::CreateEventW($INVALID, $false, $true, "${prefix}DBWIN_BUFFER_READY")
$err = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
if ($bufReady -eq $INVALID) { Abort "CreateEvent(DBWIN_BUFFER_READY) failed, error $err" }
if ($err -eq $ERROR_ALREADY_EXISTS) { Abort "DBWIN_BUFFER_READY already exists -- another listener owns DBWIN" }

$dataReady = [Dbwin]::CreateEventW($INVALID, $false, $false, "${prefix}DBWIN_DATA_READY")
$err = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
if ($dataReady -eq $INVALID) { Abort "CreateEvent(DBWIN_DATA_READY) failed, error $err" }
if ($err -eq $ERROR_ALREADY_EXISTS) { Abort "DBWIN_DATA_READY already exists -- another listener owns DBWIN" }

$view = [Dbwin]::MapViewOfFile($map, $FILE_MAP_READ, 0, 0, [UIntPtr]::new(4096))
if ($view -eq $INVALID) {
  Abort ("MapViewOfFile failed, error " +
         [Runtime.InteropServices.Marshal]::GetLastWin32Error())
}

# Create the session artifact BEFORE listening. A run that records nothing is a
# result, not a failure, and it still has to be hashable and attributable.
$startUtc   = (Get-Date).ToUniversalTime()
$startLocal = Get-Date
@(
  "# haltrace.ps1 session"
  "# start_utc   : $($startUtc.ToString('o'))"
  "# start_local : $($startLocal.ToString('o'))"
  "# host        : $env:COMPUTERNAME"
  "# user        : $env:USERNAME"
  "# elevated    : True"
  "# dbwin       : ${prefix}DBWIN_BUFFER (sole listener confirmed)"
  "# filter_asus : $([bool]$FilterAsus)"
  "# seconds     : $Seconds"
  "# clock       : lines are stamped from the Windows wall clock; correlate"
  "#               with a capture on frame.time_epoch, NOT frame.time_relative,"
  "#               and treat the alignment as approximate and manual"
) | Out-File -LiteralPath $Out -Encoding utf8

Write-Host "Listening on ${prefix}DBWIN_BUFFER  ->  $Out" -ForegroundColor Green
Write-Host "Sole listener confirmed. Now drive Armoury Crate. Ctrl+C to stop.`n" -ForegroundColor Green

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

    $now = Get-Date
    $line = "{0}  {1:HH:mm:ss.fff}  pid={2,-6} {3}" -f
            $now.ToUniversalTime().ToString('o'), $now, $pid_, $str
    $line | Tee-Object -FilePath $Out -Append
    $n++
  }
}
finally {
  Close-All
  @(
    "# end_utc     : $((Get-Date).ToUniversalTime().ToString('o'))"
    "# lines       : $n"
  ) | Out-File -LiteralPath $Out -Encoding utf8 -Append
  $item = Get-Item -LiteralPath $Out
  $hash = (Get-FileHash -LiteralPath $Out -Algorithm SHA256).Hash.ToLower()
  Write-Host "`ncaptured $n lines -> $Out" -ForegroundColor Green
  if ($n -eq 0) {
    Write-Host "  zero events. That is a RESULT, not a failure: the artifact" -ForegroundColor Yellow
    Write-Host "  below records the session and is hashed like any other." -ForegroundColor Yellow
  }
  Write-Host ("  bytes : {0}" -f $item.Length) -ForegroundColor Green
  Write-Host ("  sha256: {0}" -f $hash) -ForegroundColor Green
}
