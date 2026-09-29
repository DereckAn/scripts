<#
.SYNOPSIS
  Guided, timestamped USBPcap capture for the feature-validation run (capture 03b and later).

.DESCRIPTION
  PASSIVE ONLY. Sends nothing to the keyboard. It records USB traffic, reads the
  firmware revision from Windows, and copies the profile files Armoury Crate already wrote.

  Why this exists instead of capture.ps1:
    - It calls USBPcapCMD directly with --inject-descriptors, the same flags as captures
      02 and 03, so VID:PID resolves per address and the runs are comparable. tshark's
      extcap launch does not pass that flag.
    - It starts USBPcapCMD in the background and stops it itself. In capture 03 the
      prompt came back at once and Ctrl+C in that window never reached USBPcapCMD.
    - Each action is marked by pressing Enter, so times are exact (ms) instead of
      handwritten.

  Plans (-Plan):
    features  the run-03b list: one of each feature (log 135).
    finish    run 03d (the default): the rapid-trigger lever, per-key actuation through
              AC's "Individual key actuation point settings", and the keys not yet seen.
    deep      run 03c: the open items of log 135 section 11 -- key indices by
              per-key actuation and by macro, remap targets, per-key and all-key
              rapid trigger with DISTINCT values, dead zone, one lighting property
              at a time, profile read-back, and restoring every change.

  Outputs (all refused if they already exist -- captures are evidence):
    ..\captures\<Name>.pcap
    ..\captures\<Name>-notes.txt        action times, from/to notes, fw rev, AC version, hash
    ..\snapshots\<Name>-before-raw\     byte copy of the AC profile folder and the AC
    ..\snapshots\<Name>-after-raw\      macro folder (.GMAC), each with a sha256 manifest
    ..\snapshots\<Name>-before.json     decoded, via snap-config.ps1 (best effort)
    ..\snapshots\<Name>-after.json

  Run elevated.

.EXAMPLE
  .\feature-session.ps1                      # plan deep  -> 03c-deep
  .\feature-session.ps1 -Plan features -Name 03d-features
#>
[CmdletBinding()]
param(
  [ValidateSet('features', 'deep', 'finish')]
  [string]$Plan = 'finish',
  [string]$Name,                  # default: 03b-features / 03c-deep / 03d-finish by plan
  [string]$Interface,             # e.g. \\.\USBPcap3; default: the one the keyboard is on
  [int]$IdleSeconds = 15
)

$ErrorActionPreference = 'Stop'

if (-not $Name) { $Name = @{ features = '03b-features'; deep = '03c-deep'; finish = '03d-finish' }[$Plan] }

$FalchionVid = '0B05'
$FalchionPid = '1B7E'
$usbpcap     = 'C:\Program Files\USBPcap\USBPcapCMD.exe'
$acDir       = 'C:\ProgramData\ASUS\Framework\keyboard\ROG FALCHION ACE HFX'
$macroDir    = Join-Path $env:LOCALAPPDATA 'ASUS\Armoury Crate Service\CachedMacroProfiles'

$capDir  = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\captures'))
$snapDir = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\snapshots'))
$pcap       = Join-Path $capDir  "$Name.pcap"
$notes      = Join-Path $capDir  "$Name-notes.txt"
$rawBefore  = Join-Path $snapDir "$Name-before-raw"
$rawAfter   = Join-Path $snapDir "$Name-after-raw"
$snapBefore = Join-Path $snapDir "$Name-before.json"
$snapAfter  = Join-Path $snapDir "$Name-after.json"

function Now { (Get-Date).ToString('yyyy-MM-dd HH:mm:ss.fff') }

function Write-Note([string]$line) {
  Add-Content -LiteralPath $notes -Value $line -Encoding UTF8
  Write-Host $line
}

function Get-FirmwareRev {
  $kb = Get-PnpDevice -PresentOnly |
        Where-Object { $_.InstanceId -like "USB\VID_$FalchionVid&PID_$FalchionPid\*" } |
        Select-Object -First 1
  if (-not $kb) { return 'KEYBOARD NOT PRESENT' }
  $ids = (Get-PnpDeviceProperty -InstanceId $kb.InstanceId -KeyName DEVPKEY_Device_HardwareIds).Data
  $rev = $ids | Where-Object { $_ -match 'REV_([0-9A-F]{4})' } | Select-Object -First 1
  if ($rev -match 'REV_([0-9A-F]{4})') { return $Matches[1] }
  return 'unknown'
}

function Get-AcVersion {
  $p = Get-AppxPackage -Name 'B9ECED6F.ArmouryCrate' -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($p) { return [string]$p.Version }
  return 'unknown'
}

function Test-CaptureMagic($path) {
  $head = [byte[]]::new(4)
  $fs = [IO.File]::Open($path, 'Open', 'Read', 'ReadWrite')
  try { $n = $fs.Read($head, 0, 4) } finally { $fs.Dispose() }
  if ($n -lt 4) { return $false }
  $hex = ($head | ForEach-Object { '{0:X2}' -f $_ }) -join ''
  return @('D4C3B2A1', 'A1B2C3D4', '4D3CB2A1', 'A1B23C4D') -contains $hex
}

function Save-RawProfiles($dest) {
  # profiles\ = the AC profile folder, macros\ = the .GMAC files. A macro is stored in
  # the profile only as a path to its .GMAC (log 135 s6.5), so both are needed.
  try {
    if (-not (Test-Path -LiteralPath $acDir)) { return "AC profile folder not found: $acDir" }
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Copy-Item -LiteralPath $acDir -Destination (Join-Path $dest 'profiles') -Recurse
    if (Test-Path -LiteralPath $macroDir) {
      Copy-Item -LiteralPath $macroDir -Destination (Join-Path $dest 'macros') -Recurse
    }
    $manifest = Get-ChildItem -LiteralPath $dest -Recurse -File | ForEach-Object {
      '{0}  {1}  {2}  {3}' -f (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower(),
        $_.Length, $_.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'), $_.FullName.Substring($dest.Length + 1)
    }
    $manifest | Set-Content -LiteralPath (Join-Path $dest 'SHA256SUMS.txt') -Encoding UTF8
    return "saved $(@($manifest).Count) files -> $dest"
  } catch { return "raw profile copy FAILED: $($_.Exception.Message)" }
}

function Save-DecodedProfiles($dest, $diffAgainst) {
  try {
    $snap = Join-Path $PSScriptRoot 'snap-config.ps1'
    if ($diffAgainst -and (Test-Path -LiteralPath $diffAgainst)) {
      & $snap -AllProfiles -Save $dest -Diff $diffAgainst | Out-Host
    } else {
      & $snap -AllProfiles -Save $dest | Out-Host
    }
    return "snap-config exit $LASTEXITCODE -> $dest"
  } catch { return "snap-config FAILED (non-fatal): $($_.Exception.Message)" }
}

function Wait-Idle([datetime]$since, [int]$secs) {
  $left = [int][math]::Ceiling($secs - ((Get-Date) - $since).TotalSeconds)
  while ($left -gt 0) {
    Write-Host -NoNewline "`r  hands off Armoury Crate... $left s  "
    Start-Sleep -Seconds 1
    $left--
  }
  Write-Host "`r  ok, next action.                     "
}

# --- preconditions ------------------------------------------------------------------

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Host 'NOT ELEVATED -- open PowerShell as Administrator and run this again.' -ForegroundColor Red
  exit 1
}
if (-not (Test-Path -LiteralPath $usbpcap)) { Write-Host "USBPcapCMD not found at $usbpcap" -ForegroundColor Red; exit 1 }

foreach ($p in @($pcap, $notes, $rawBefore, $rawAfter, $snapBefore, $snapAfter)) {
  if (Test-Path -LiteralPath $p) {
    Write-Host "REFUSING: $p already exists. Captures are evidence; pick another -Name." -ForegroundColor Red
    exit 1
  }
}

if (Get-Process USBPcapCMD -ErrorAction SilentlyContinue) {
  Write-Host 'A USBPcapCMD capture is already running. Stop it first:  Stop-Process -Name USBPcapCMD' -ForegroundColor Red
  exit 1
}

if (-not $Interface) {
  # USBPcapCMD is a GUI-subsystem exe: PowerShell's & neither waits for it nor captures
  # its stdout (that is also why capture 03 "returned" at once). cmd /c does both.
  # --extcap-interfaces does not list reliably this way, so probe each control device.
  foreach ($n in 1..16) {
    $i = "\\.\USBPcap$n"
    $cfg = cmd /c "`"$usbpcap`" --extcap-interface $i --extcap-config 2>nul"
    if ($cfg | Select-String -SimpleMatch 'FALCHION' -Quiet) { $Interface = $i; break }
  }
  if (-not $Interface) { Write-Host 'Could not find the keyboard on any USBPcap interface.' -ForegroundColor Red; exit 1 }
}

$fwBefore = Get-FirmwareRev
if ($fwBefore -eq 'KEYBOARD NOT PRESENT') { Write-Host 'Keyboard not connected.' -ForegroundColor Red; exit 1 }

Write-Host "`nkeyboard firmware : REV_$fwBefore" -ForegroundColor Cyan
Write-Host "capture interface : $Interface" -ForegroundColor Cyan
Write-Host "output            : $pcap`n" -ForegroundColor Cyan

# Armoury Crate should be closed so its launch lands inside the capture, like run 03.
while (Get-Process ArmouryCrate -ErrorAction SilentlyContinue) {
  Write-Host 'Armoury Crate is open. Close it fully: the window AND the system-tray icon (right-click > Exit).' -ForegroundColor Yellow
  $r = Read-Host "Press Enter when closed (or type 'skip' to continue with it open)"
  if ($r -eq 'skip') { $acOpenAtStart = $true; break }
}

New-Item -ItemType Directory -Force -Path $capDir, $snapDir | Out-Null
Write-Note "# $Name -- feature validation run (plan: $Plan), written by tools/feature-session.ps1"
Write-Note "host              : $env:COMPUTERNAME"
Write-Note "session start     : $(Now) (local, UTC$((Get-Date).ToString('zzz')))"
Write-Note "keyboard fw before: REV_$fwBefore"
Write-Note "AC version        : $(Get-AcVersion)"
Write-Note "AC open at start  : $(if ($acOpenAtStart) { 'YES (skipped)' } else { 'no' })"
Write-Note "interface         : $Interface"
Write-Note "command           : USBPcapCMD -d $Interface -A --inject-descriptors -s 65535 -b 134217728 -o $pcap"

Write-Host "`nsnapshotting AC profiles (before)..." -ForegroundColor DarkGray
Write-Note "profiles before   : $(Save-RawProfiles $rawBefore)"
Write-Note "decoded before    : $(Save-DecodedProfiles $snapBefore $null)"

# --- start capture ------------------------------------------------------------------

$capArgs = @('-d', $Interface, '-A', '--inject-descriptors', '-s', '65535', '-b', '134217728', '-o', "`"$pcap`"")
Start-Process -FilePath $usbpcap -ArgumentList $capArgs -WindowStyle Hidden | Out-Null
Start-Sleep -Seconds 3
$capPids = @(Get-Process USBPcapCMD -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
if (-not $capPids -or -not (Test-Path -LiteralPath $pcap)) {
  Write-Note "CAPTURE FAILED TO START at $(Now)"
  exit 1
}
$s1 = (Get-Item -LiteralPath $pcap).Length; Start-Sleep -Seconds 2; $s2 = (Get-Item -LiteralPath $pcap).Length
Write-Note "capture started   : $(Now)  pid(s) $($capPids -join ',')  size $s1 -> $s2 bytes"
if ($s2 -le $s1) { Write-Host 'WARNING: file is not growing yet. Continuing; it will be checked at the end.' -ForegroundColor Yellow }

# --- guided actions -----------------------------------------------------------------

$plans = @{}
$plans['finish'] = @(
  # log 136 s5. AC's Trigger page (owner's screenshot): the left panel holds global
  # actuation, "Individual key actuation point settings: Edit" and the dead zones; the
  # right panel holds Press/Release, applied only to the keys under "Assign the keys for
  # Rapid Trigger: Edit". Rapid trigger ON/OFF is the physical LEVER.
  @{ Id = '0';   Do = 'Open Armoury Crate, Falchion page, profile 1, Trigger tab. Mark when loaded.'; Ask = 'what does it say next to "Rapid Trigger" (ON/OFF)?' },
  # --- the lever: does the keyboard report it? ---
  @{ Id = '1a';  Do = 'Flip the rapid-trigger LEVER on the keyboard ONCE. Do not touch AC.'; Ask = 'did the ON/OFF label in AC change? to what?' },
  @{ Id = '1b';  Do = 'Flip the LEVER back ONCE.'; Ask = 'label now?' },
  # --- per-key actuation, the predicted 51 4f, never observed ---
  @{ Id = '2a';  Do = 'LEFT panel: "Individual key actuation point settings" -> Edit. Select ONLY the P key, set it to 1.5 mm, save/apply.'; Ask = 'what did the Edit screen look like / button names?' },
  @{ Id = '2b';  Do = 'Same Edit screen: select ONLY the L key, set it to 3.0 mm (different on purpose), save/apply.'; Ask = 'actual value set' },
  @{ Id = '2c';  Do = 'Put P and L back to the global value (remove them from individual settings), save/apply. Do NOT use the big Reset button.'; Ask = 'how did you remove them?' },
  # --- the keys not yet seen on the wire ---
  @{ Id = '3a';  Do = 'Record a macro named KEYS2, slowly:  - = [ ] \ ; '' , . /  Backspace  Enter  Del  PgUp  PgDn  Up  Caps  Caps  Esc  (Esc last; if Esc stops the recording, fine). Stop with the mouse. Save.'; Ask = 'anything that did not record?' },
  @{ Id = '3b';  Do = 'Assign macro KEYS2 to the Ins key. Apply.'; Ask = $null },
  @{ Id = '3c';  Do = 'Restore the Ins key to Default. Apply.'; Ask = $null },
  @{ Id = '4';   Do = 'CLOSE Armoury Crate fully: window AND tray icon. Mark once it is gone.'; Ask = $null }
)
$plans['deep'] = @(
  # --- start: AC launch, then profile read-back (log 135 s11 h) ---
  @{ Id = '0';   Do = 'Open Armoury Crate and go to the Falchion Ace HFX page. Mark when it has fully loaded.'; Ask = 'which profile is active?' },
  @{ Id = '1a';  Do = 'Switch to profile 2 (once).'; Ask = $null },
  @{ Id = '1b';  Do = 'Switch to profile 3 (once).'; Ask = $null },
  @{ Id = '1c';  Do = 'Switch to profile 4 (once).'; Ask = $null },
  @{ Id = '1d';  Do = 'Switch to profile 1 (once). STAY ON PROFILE 1 for every step below.'; Ask = $null },
  # --- per-key actuation: physical key numbers + the predicted 51 4f (s11 a, e) ---
  @{ Id = '2a';  Do = 'PER-KEY actuation (not global): select row 3 keys ONE AT A TIME, left to right: Caps, A, S, D, F, G, H, J, K, L, ;, '', Enter. Set them to 1.5 mm and Apply.'; Ask = 'did every key accept? any key it would not select?' },
  @{ Id = '2b';  Do = 'PER-KEY actuation: select the bottom row ONE AT A TIME, left to right (Ctrl, Win, Alt, Space, Alt, then any others it lets you pick, then Left, Down, Right). Set 1.5 mm, Apply.'; Ask = 'which keys, in the order you clicked' },
  @{ Id = '2c';  Do = 'Put per-key actuation BACK: set all those keys back to the global value (or reset per-key actuation). Apply.'; Ask = 'how did you reset it (button name)?' },
  # --- remap target encoding on ONE source key (s11 b, i) ---
  @{ Id = '3a';  Do = 'Remap the Ins key -> A. Apply.'; Ask = 'which key did you use as the source, if not Ins?' },
  @{ Id = '3b';  Do = 'Remap the same key -> 1 (the digit). Apply.'; Ask = $null },
  @{ Id = '3c';  Do = 'Remap the same key -> Space. Apply.'; Ask = $null },
  @{ Id = '3d';  Do = 'Remap the same key -> Right Shift. Apply.'; Ask = $null },
  @{ Id = '3e';  Do = 'Restore that key to its DEFAULT (reset/restore button). Apply.'; Ask = 'button name used' },
  @{ Id = '3f';  Do = 'Restore Tab to DEFAULT (it is still remapped to Right Shift from run 03b). Apply.'; Ask = $null },
  # --- rapid trigger with DISTINCT values (s11 c, d) ---
  @{ Id = '4a';  Do = 'Rapid trigger, ALL keys (global): set press 0.2 mm and release 0.5 mm (different on purpose). Apply.'; Ask = 'actual values set' },
  @{ Id = '4b';  Do = 'Rapid trigger, PER-KEY: select ONLY the O key. Turn its rapid trigger ON with press 0.1 and release 0.4. Apply.'; Ask = 'actual values set' },
  @{ Id = '4c';  Do = 'Per-key: turn rapid trigger OFF for the O key. Apply.'; Ask = $null },
  @{ Id = '4d';  Do = 'Global rapid trigger back to press 0.3 / release 0.3. Apply.'; Ask = $null },
  # --- dead zone (s11 f) ---
  @{ Id = '5a';  Do = 'Dead zone: change the TOP dead zone one step. Apply.'; Ask = 'from -> to' },
  @{ Id = '5b';  Do = 'Dead zone: change the BOTTOM dead zone one step. Apply.'; Ask = 'from -> to' },
  @{ Id = '5c';  Do = 'Dead zone: put both back. Apply.'; Ask = $null },
  # --- macro key numbering, multi-frame upload, unassign (s11 a, i) ---
  @{ Id = '6a';  Do = 'Record a macro named ROWS: type slowly  q w e r t y u i o p  a s d f g h j k l  z x c v b n m  1 2 3 4 5 6 7 8 9 0. Stop recording with the STOP BUTTON (keyboard), not a mouse click if you can. Save.'; Ask = 'anything you mistyped?' },
  @{ Id = '6b';  Do = 'Assign macro ROWS to the Ins key. Apply.'; Ask = $null },
  @{ Id = '6c';  Do = 'Restore the Ins key to DEFAULT (unassign the macro). Apply.'; Ask = $null },
  # --- lighting, ONE property per step (s11 g) ---
  @{ Id = '7a';  Do = 'Lighting: set effect to STATIC (if it already is, pick another effect, then Static).'; Ask = 'effect before' },
  @{ Id = '7b';  Do = 'Lighting: set colour to pure GREEN (R0 G255 B0).'; Ask = $null },
  @{ Id = '7c';  Do = 'Lighting: set colour to pure BLUE (R0 G0 B255).'; Ask = $null },
  @{ Id = '7d';  Do = 'Lighting: brightness ONE step or type an exact value.'; Ask = 'from -> to' },
  @{ Id = '7e';  Do = 'Lighting: switch to an ANIMATED effect (e.g. Rainbow/Breathing) and change its SPEED once.'; Ask = 'effect name, speed from -> to' },
  # --- end: close AC so its post-edit writes are recorded (log 135 s9) ---
  @{ Id = '8';   Do = 'CLOSE Armoury Crate fully: window AND tray icon. Mark once it is gone.'; Ask = $null }
)

$plans['features'] = @(
  @{ Id = '0';  Do = 'Open Armoury Crate and go to the Falchion Ace HFX page. Mark when the page has fully loaded.'; Ask = $null },
  @{ Id = '1';  Do = 'Switch profile 1 -> 2. ONCE only.'; Ask = 'anything odd? (Enter = no)' },
  @{ Id = '2';  Do = 'Switch profile 2 -> 1. ONCE only.'; Ask = 'anything odd? (Enter = no)' },
  @{ Id = '3';  Do = 'Actuation: change the GLOBAL value one step. Click Apply/Save if there is one.'; Ask = 'from -> to (e.g. 2.0 -> 2.1 mm)' },
  @{ Id = '4';  Do = 'Rapid trigger: change press and/or release value. Apply/Save if needed.'; Ask = 'which value(s), from -> to' },
  @{ Id = '5';  Do = 'Remap ONE ordinary key -- a DIFFERENT key than in run 03 (no Fn/reserved keys).'; Ask = 'key -> mapped to' },
  @{ Id = '6a'; Do = 'Macro: create/record macro A (a, b, c) in the editor and SAVE it. Do NOT assign it yet.'; Ask = 'macro name / anything odd' },
  @{ Id = '6b'; Do = 'Macro: ASSIGN macro A to one key and Apply.'; Ask = 'which key' },
  @{ Id = '6c'; Do = 'Macro: create macro B and SAVE it (do not assign).'; Ask = 'macro name / anything odd' },
  @{ Id = '6d'; Do = 'Macro: ASSIGN macro B to another key and Apply.'; Ask = 'which key' },
  @{ Id = '7';  Do = 'Lighting: change brightness ONCE (single click/step if you can).'; Ask = 'from -> to' }
)

$actions = $plans[$Plan]

Write-Host "`n=================================================================" -ForegroundColor Green
Write-Host " CAPTURE RUNNING. Keep this window visible next to Armoury Crate." -ForegroundColor Green
Write-Host " For each step: do it in AC, then come back and press Enter." -ForegroundColor Green
Write-Host " Type 'skip' instead if the step is impossible (e.g. no macro UI)." -ForegroundColor Green
Write-Host " DECLINE any firmware update prompt." -ForegroundColor Yellow
Write-Host "=================================================================`n" -ForegroundColor Green

Wait-Idle (Get-Date) $IdleSeconds
Write-Note ''
Write-Note '# actions (time = when Enter was pressed, just AFTER the action)'

foreach ($a in $actions) {
  Write-Host "`n[$($a.Id)] $($a.Do)" -ForegroundColor Cyan
  $r = Read-Host '    press Enter right AFTER doing it (or type skip)'
  $t = Get-Date
  if ($r -eq 'skip') {
    Write-Note ("ACTION {0,-3} SKIPPED  {1}  -- {2}" -f $a.Id, $t.ToString('HH:mm:ss.fff'), $a.Do)
    continue
  }
  $note = ''
  if ($a.Ask) { $note = Read-Host "    $($a.Ask)" }
  Write-Note ("ACTION {0,-3} {1}  {2}  | {3}" -f $a.Id, $t.ToString('HH:mm:ss.fff'), $a.Do, $note)
  Wait-Idle $t $IdleSeconds
}

Write-Host "`nAnything else you want marked? Type a label and press Enter (e.g. 'AC froze')." -ForegroundColor Cyan
while ($true) {
  $r = Read-Host "    label, or just Enter to finish"
  if (-not $r) { break }
  Write-Note ("MARK       {0}  {1}" -f (Get-Date).ToString('HH:mm:ss.fff'), $r)
}

$upd = Read-Host "`nDid any update prompt appear? (Y/N, plus details)"
$odd = Read-Host 'Anything unexpected?'
Write-Note ''
Write-Note "update prompt     : $upd"
Write-Note "unexpected        : $odd"

# --- stop capture -------------------------------------------------------------------

Write-Host "`nfinal idle period, do not touch Armoury Crate:" -ForegroundColor DarkGray
# AC rewrote a profile 26 s after capture 03b stopped (log 135 s9); wait at least 30 s.
Wait-Idle (Get-Date) ([math]::Max($IdleSeconds, 30))
$stopAt = Now
Stop-Process -Id $capPids -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
$still = @(Get-Process USBPcapCMD -ErrorAction SilentlyContinue)
Write-Note "capture stopped   : $stopAt  (Stop-Process by script$(if ($still) { '; WARNING USBPcapCMD STILL RUNNING' }))"

$ok = (Test-Path -LiteralPath $pcap -PathType Leaf) -and ((Get-Item -LiteralPath $pcap).Length -gt 0) -and (Test-CaptureMagic $pcap)
if ($ok) {
  $item = Get-Item -LiteralPath $pcap
  $hash = (Get-FileHash -LiteralPath $pcap -Algorithm SHA256).Hash.ToLower()
  Write-Note "pcap bytes        : $($item.Length)"
  Write-Note "pcap sha256       : $hash"
} else {
  Write-Note 'pcap              : FAILED CHECK (missing, empty or not a pcap) -- left in place for inspection'
}

$fwAfter = Get-FirmwareRev
Write-Note "keyboard fw after : REV_$fwAfter$(if ($fwAfter -ne $fwBefore) { '   <<< CHANGED -- TELL THE REVIEW SESSION' })"

Write-Host "`nsnapshotting AC profiles (after)..." -ForegroundColor DarkGray
Write-Note "profiles after    : $(Save-RawProfiles $rawAfter)"
Write-Note "decoded after     : $(Save-DecodedProfiles $snapAfter $snapBefore)"
Write-Note "session end       : $(Now)"

Write-Host "`nDONE. Do not rename or edit $Name.pcap." -ForegroundColor Green
Write-Host "Notes: $notes" -ForegroundColor Green
