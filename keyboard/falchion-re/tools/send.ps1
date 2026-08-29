<#
.SYNOPSIS
  Sends a raw 64-byte command on the Falchion's 0xFF00 vendor channel and reads the reply.

.DESCRIPTION
  Opens HID\VID_0B05&PID_1B7E&MI_01 (usage page 0xFF00) and writes a 65-byte report:
  a leading 0x00 report-ID placeholder followed by the 64-byte payload. Then reads one
  input report with a timeout.

  WARNING: every invocation writes an undocumented vendor-HID report. Omitting -Commit
  avoids the recorded 0x50 0x55 persistent commit but does not make the command read-only;
  live device state may still change. Retained for historical protocol reproducibility.
  Do not run during firmware preservation without a separate approved write-test plan.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$Bytes,
  [switch]$Commit,
  [int]$TimeoutMs = 1500
)

$ErrorActionPreference = 'Stop'

$src = @'
using System;
using System.Runtime.InteropServices;
using System.Threading;
public class RawHid {
  const uint GENERIC_READ=0x80000000, GENERIC_WRITE=0x40000000;
  const uint FILE_SHARE_READ=1, FILE_SHARE_WRITE=2;
  const uint OPEN_EXISTING=3, FILE_FLAG_OVERLAPPED=0x40000000;
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
  static extern IntPtr CreateFileW(string n,uint acc,uint share,IntPtr sa,uint disp,uint flags,IntPtr tmpl);
  [DllImport("kernel32.dll",SetLastError=true)]
  static extern bool WriteFile(IntPtr h,byte[] b,uint n,IntPtr written,IntPtr ov);
  [DllImport("kernel32.dll",SetLastError=true)]
  static extern bool ReadFile(IntPtr h,byte[] b,uint n,IntPtr read,IntPtr ov);
  [DllImport("kernel32.dll",SetLastError=true)]
  static extern bool GetOverlappedResult(IntPtr h,IntPtr ov,out uint n,bool wait);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool CancelIo(IntPtr h);
  [DllImport("kernel32.dll",SetLastError=true)] public static extern bool CloseHandle(IntPtr h);
  [DllImport("kernel32.dll",SetLastError=true)]
  static extern IntPtr CreateEventW(IntPtr sa,bool manual,bool init,string name);
  [DllImport("kernel32.dll",SetLastError=true)] static extern uint WaitForSingleObject(IntPtr h,uint ms);

  public static IntPtr Open(string path){
    IntPtr h = CreateFileW(path, GENERIC_READ|GENERIC_WRITE, FILE_SHARE_READ|FILE_SHARE_WRITE,
                           IntPtr.Zero, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, IntPtr.Zero);
    if(h.ToInt64()==-1) throw new Exception("open failed, win32="+Marshal.GetLastWin32Error());
    return h;
  }
  static IntPtr NewOv(IntPtr evt){
    IntPtr ov = Marshal.AllocHGlobal(32);
    for(int i=0;i<32;i++) Marshal.WriteByte(ov,i,0);
    Marshal.WriteIntPtr(ov, IntPtr.Size==8?24:16, evt);
    return ov;
  }
  public static void Write(IntPtr h, byte[] buf, int timeoutMs){
    IntPtr evt = CreateEventW(IntPtr.Zero,true,false,null);
    IntPtr ov = NewOv(evt);
    bool ok = WriteFile(h, buf, (uint)buf.Length, IntPtr.Zero, ov);
    if(!ok){
      int err = Marshal.GetLastWin32Error();
      if(err != 997) { Marshal.FreeHGlobal(ov); CloseHandle(evt); throw new Exception("write failed, win32="+err); }
      if(WaitForSingleObject(evt,(uint)timeoutMs)!=0){ CancelIo(h); Marshal.FreeHGlobal(ov); CloseHandle(evt); throw new Exception("write timeout"); }
    }
    uint n; GetOverlappedResult(h,ov,out n,false);
    Marshal.FreeHGlobal(ov); CloseHandle(evt);
  }
  public static byte[] Read(IntPtr h, int len, int timeoutMs){
    byte[] buf = new byte[len];
    IntPtr evt = CreateEventW(IntPtr.Zero,true,false,null);
    IntPtr ov = NewOv(evt);
    bool ok = ReadFile(h, buf, (uint)len, IntPtr.Zero, ov);
    if(!ok){
      int err = Marshal.GetLastWin32Error();
      if(err != 997){ Marshal.FreeHGlobal(ov); CloseHandle(evt); throw new Exception("read failed, win32="+err); }
      if(WaitForSingleObject(evt,(uint)timeoutMs)!=0){ CancelIo(h); Marshal.FreeHGlobal(ov); CloseHandle(evt); return null; }
    }
    uint n; GetOverlappedResult(h,ov,out n,false);
    Marshal.FreeHGlobal(ov); CloseHandle(evt);
    return buf;
  }
}
'@
if (-not ('RawHid' -as [type])) { Add-Type -TypeDefinition $src }

function Send-Cmd($h, [byte[]]$payload, [int]$timeout) {
  $rep = New-Object byte[] 65
  $rep[0] = 0
  [Array]::Copy($payload, 0, $rep, 1, [Math]::Min(64, $payload.Length))
  [RawHid]::Write($h, $rep, $timeout)
  $r = [RawHid]::Read($h, 65, $timeout)
  if ($null -eq $r) { return $null }
  $out = New-Object byte[] 64
  [Array]::Copy($r, 1, $out, 0, 64)
  ,$out
}
function Hex($b, $n=16) { if($null -eq $b){return '<no reply>'}; (($b[0..([Math]::Min($n,$b.Length)-1)] | ForEach-Object { '{0:X2}' -f $_ }) -join ' ') }

# --- locate the 0xFF00 interface ---
$dev = Get-PnpDevice -Class HIDClass -PresentOnly |
       Where-Object { $_.InstanceId -like 'HID\VID_0B05&PID_1B7E&MI_01*' } | Select-Object -First 1
if (-not $dev) { throw "MI_01 (0xFF00) interface not found" }
$path = "\\?\" + ($dev.InstanceId -replace '\\','#') + "#{4d1e55b2-f16f-11cf-88cb-001111000030}"
Write-Host "device : $($dev.InstanceId)" -ForegroundColor Cyan

$payload = New-Object byte[] 64
$i = 0
foreach ($tok in ($Bytes -split '[\s,]+' | Where-Object { $_ })) {
  $payload[$i] = [Convert]::ToByte(($tok -replace '^0[xX]',''), 16); $i++
}

$h = [RawHid]::Open($path)
try {
  Write-Host "`nOUT    $(Hex $payload)" -ForegroundColor Yellow
  $r = Send-Cmd $h $payload $TimeoutMs
  Write-Host "IN     $(Hex $r)" -ForegroundColor Green

  if ($null -eq $r) {
    Write-Host "`n=> NO REPLY (timeout)" -ForegroundColor Red
  } elseif ($r[0] -eq 0xFF -and $r[1] -eq 0xAA) {
    Write-Host "`n=> FF AA -- DEVICE REJECTED THE COMMAND (firmware-level lock)" -ForegroundColor Red
  } elseif ($r[0] -eq $payload[0] -and $r[1] -eq $payload[1]) {
    Write-Host "`n=> header echoed -- delivery observed; effect/acceptance UNKNOWN" -ForegroundColor Yellow
    $same = $true; 0..7 | ForEach-Object { if ($r[$_] -ne $payload[$_]) { $same = $false } }
    if ($same) { Write-Host "   full 8-byte echo (identical to request; not proof of effect)" -ForegroundColor Yellow }
  } else {
    Write-Host "`n=> unexpected reply shape" -ForegroundColor Yellow
  }

  if ($Commit) {
    $c = New-Object byte[] 64; $c[0]=0x50; $c[1]=0x55
    Write-Host "`nOUT    $(Hex $c)  (commit to flash)" -ForegroundColor Yellow
    $r2 = Send-Cmd $h $c $TimeoutMs
    Write-Host "IN     $(Hex $r2)" -ForegroundColor Green
  } else {
    Write-Host "`n(no 0x50 0x55 persistent commit requested; live state may have changed)" -ForegroundColor DarkGray
  }
}
finally { [void][RawHid]::CloseHandle($h) }
