<#
.SYNOPSIS
  Snapshots and diffs the Armoury Crate on-disk profiles for the Falchion Ace HFX.

.DESCRIPTION
  AC stores each keyboard profile as base64( percent-encode( JSON ) ) inside an XML
  wrapper. This decodes them to plain JSON, records where each one came from, and diffs
  two snapshots.

  Read-only with respect to the keyboard -- this only reads files AC already wrote.

  WHAT CHANGED (log 131, finding 4). The previous version saved the whole decoded
  configuration but compared only `button.keyboardButton`, so it printed "NO CHANGE"
  after a global rapid-trigger, polling-rate, Speed Tap, dead-zone, lighting or lever
  change. The diff is now a DETERMINISTIC RECURSIVE COMPARISON of every path in the
  decoded model, so "NO CHANGE" means the complete compared model is equal. Nothing is
  hand-listed, so nothing can be forgotten.

  -AllProfiles snapshots EVERY fp_*_config_*.xml in the folder, not just profile 3, and
  records each one's source filename, full path, mtime and SHA-256 alongside its decoded
  JSON. That is what makes a profile-switch experiment meaningful: the output names the
  file that changed.

  Snapshots are evidence and an existing -Save path is REFUSED. Use -Unique for a
  timestamped name.

  The offline twin of the diff is tool/profile_diff.py, which the unit suite drives
  against notes/ac-profile3-decoded.json plus controlled mutations of each required
  setting category. `python3 tool/profile_diff.py --check` fails if the two drift apart.

  Workflow:
    1) .\snap-config.ps1 -AllProfiles -Save ..\snapshots\before.json
    2) change ONE thing in Armoury Crate, hit Apply
    3) .\snap-config.ps1 -AllProfiles -Save ..\snapshots\after.json -Diff ..\snapshots\before.json

.EXAMPLE
  .\snap-config.ps1 -AllProfiles -Save ..\snapshots\before.json
  .\snap-config.ps1 -AllProfiles -Save ..\snapshots\after.json -Diff ..\snapshots\before.json
#>
[CmdletBinding()]
param(
  [string]$Profile,                       # one profile id; default is every profile
  [string]$Model   = '024080600167',
  [string]$Save,
  [string]$Diff,
  [switch]$AllProfiles,
  [switch]$Unique,                        # timestamp -Save so it cannot collide
  [switch]$Watch
)

$ErrorActionPreference = 'Stop'
$dir = "C:\ProgramData\ASUS\Framework\keyboard\ROG FALCHION ACE HFX"

# CANONICAL-BEGIN profile_diff.py owns this contract
# Snapshot object : tool, capturedUtc, profiles[]
# Each profile    : file, path, mtime, sha256, config
# The diff is a recursive comparison of every path under `config`.
# CANONICAL-END

function Get-ProfileFiles {
  if (-not (Test-Path -LiteralPath $dir)) { throw "Armoury Crate profile folder not found: $dir" }
  $pattern = if ($AllProfiles -or -not $Profile) { "fp_*_config_$Model.xml" }
             else { "fp_${Profile}_config_$Model.xml" }
  $files = @(Get-ChildItem -LiteralPath $dir -Filter $pattern | Sort-Object Name)
  if ($files.Count -eq 0) {
    Write-Host "No profile XML matched $pattern in $dir" -ForegroundColor Red
    Write-Host "Available:" -ForegroundColor Yellow
    Get-ChildItem -LiteralPath $dir -Filter *.xml -ErrorAction SilentlyContinue |
      ForEach-Object { "  $($_.Name)" }
    exit 1
  }
  ,$files
}

function Get-Config($path) {
  $b64 = ([xml](Get-Content -LiteralPath $path -Raw)).root.device_type.device.function.file_data
  $txt = [uri]::UnescapeDataString([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64)))
  $txt | ConvertFrom-Json
}

function Get-Snapshot {
  $profiles = foreach ($f in Get-ProfileFiles) {
    [pscustomobject]@{
      file   = $f.Name
      path   = $f.FullName
      mtime  = $f.LastWriteTimeUtc.ToString('o')
      sha256 = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash.ToLower()
      config = Get-Config $f.FullName
    }
  }
  [pscustomobject]@{
    tool        = 'snap-config.ps1'
    capturedUtc = (Get-Date).ToUniversalTime().ToString('o')
    profiles    = @($profiles)
  }
}

# The comparison representation of one scalar. It carries the JSON TYPE as
# well as the value, because "$value" alone makes the number 1 and the string
# "1" equal, and $true and the string "true" equal. tool/profile_diff.py is
# specified to produce exactly these same strings.
function Get-Canonical($v) {
  if ($null -eq $v) { return 'null' }
  if ($v -is [bool]) { if ($v) { return 'bool:true' } else { return 'bool:false' } }
  if (($v -is [int]) -or ($v -is [long]) -or ($v -is [double]) -or
      ($v -is [decimal]) -or ($v -is [single])) {
    $inv = [Globalization.CultureInfo]::InvariantCulture
    $d = [double]$v
    if ($d -eq [math]::Truncate($d)) { return 'num:' + ([long]$d).ToString($inv) }
    return 'num:' + $d.ToString('R', $inv)
  }
  return 'str:' + [string]$v
}

# Deterministic recursive flatten: path -> canonical scalar, for EVERY leaf in
# the model. A list index is part of the path, so a reordered colour array or
# preKeyRapidTriggerList counts as a change.
function Get-Flat($value, $prefix = '', $acc = $null) {
  if ($null -eq $acc) { $acc = [ordered]@{} }
  if ($value -is [System.Management.Automation.PSCustomObject]) {
    foreach ($p in ($value.PSObject.Properties | Sort-Object Name)) {
      Get-Flat $p.Value "$prefix.$($p.Name)" $acc | Out-Null
    }
  } elseif ($value -is [System.Collections.IDictionary]) {
    foreach ($k in ($value.Keys | Sort-Object)) {
      Get-Flat $value[$k] "$prefix.$k" $acc | Out-Null
    }
  } elseif (($value -is [System.Collections.IEnumerable]) -and ($value -isnot [string])) {
    $i = 0
    foreach ($item in $value) { Get-Flat $item "$prefix[$i]" $acc | Out-Null; $i++ }
  } else {
    $acc[$(if ($prefix) { $prefix } else { '.' })] = Get-Canonical $value
  }
  $acc
}

function Compare-Config($old, $new) {
  $a = Get-Flat $old
  $b = Get-Flat $new
  $keys = [System.Collections.Generic.SortedSet[string]]::new()
  foreach ($k in $a.Keys) { [void]$keys.Add($k) }
  foreach ($k in $b.Keys) { [void]$keys.Add($k) }
  foreach ($k in $keys) {
    $inA = $a.Contains($k); $inB = $b.Contains($k)
    if (-not $inA)      { [pscustomobject]@{ Path=$k; Kind='added';   Old=$null;  New=$b[$k] } }
    elseif (-not $inB)  { [pscustomobject]@{ Path=$k; Kind='removed'; Old=$a[$k]; New=$null  } }
    elseif ($a[$k] -cne $b[$k]) {
                          [pscustomobject]@{ Path=$k; Kind='changed'; Old=$a[$k]; New=$b[$k] } }
  }
}

function Show-Src($s) {
  $n = 0
  if ([int]::TryParse($s, [ref]$n)) {
    $row = ($n -shr 8); $col = ($n -band 0xFF)
    $layer = if ($col -ge 50) { "Fn  (base col $($col - 50))" } else { 'base' }
    return "{0} = 0x{0:X4} -> row {1} col {2}  [{3}]" -f $n, $row, $col, $layer
  }
  return $s
}

$snap = Get-Snapshot
Write-Host "folder : $dir" -ForegroundColor Cyan
foreach ($p in $snap.profiles) {
  Write-Host ("  {0}  mtime {1}  sha256 {2}" -f $p.file, $p.mtime, $p.sha256) -ForegroundColor Cyan
}

if ($Save) {
  if ($Unique) {
    $dirPart  = Split-Path $Save -Parent
    $basePart = [IO.Path]::GetFileNameWithoutExtension($Save)
    $extPart  = [IO.Path]::GetExtension($Save)
    $leaf     = "$basePart-$(Get-Date -Format 'yyyyMMdd-HHmmss')$extPart"
    $Save     = if ($dirPart) { Join-Path $dirPart $leaf } else { $leaf }
  }
  if (Test-Path -LiteralPath $Save) {
    Write-Host "REFUSING: $Save already exists." -ForegroundColor Red
    Write-Host "A snapshot is the before-state of an experiment and is not overwritten." -ForegroundColor Red
    Write-Host "Choose another name, or re-run with -Unique." -ForegroundColor Yellow
    exit 1
  }
  $snap | ConvertTo-Json -Depth 40 | Out-File -LiteralPath $Save -Encoding utf8
  $h = (Get-FileHash -LiteralPath $Save -Algorithm SHA256).Hash.ToLower()
  Write-Host "saved  : $Save" -ForegroundColor Green
  Write-Host ("  bytes : {0}" -f (Get-Item -LiteralPath $Save).Length) -ForegroundColor Green
  Write-Host ("  sha256: {0}" -f $h) -ForegroundColor Green
}

if ($Diff) {
  if (-not (Test-Path -LiteralPath $Diff)) { Write-Host "baseline not found: $Diff" -ForegroundColor Red; exit 1 }
  $old = Get-Content -LiteralPath $Diff -Raw | ConvertFrom-Json
  if (-not $old.profiles) {
    Write-Host "baseline $Diff predates the -AllProfiles snapshot format." -ForegroundColor Red
    Write-Host "It has no per-file identity, so a change cannot be attributed. Re-take it." -ForegroundColor Red
    exit 1
  }

  $oldByFile = @{}; foreach ($p in $old.profiles)  { $oldByFile[$p.file] = $p }
  $newByFile = @{}; foreach ($p in $snap.profiles) { $newByFile[$p.file] = $p }

  $names = [System.Collections.Generic.SortedSet[string]]::new()
  foreach ($k in $oldByFile.Keys) { [void]$names.Add($k) }
  foreach ($k in $newByFile.Keys) { [void]$names.Add($k) }

  $changedFiles = 0; $changes = 0
  foreach ($name in $names) {
    if (-not $oldByFile.ContainsKey($name)) {
      Write-Host "`n+ $name  added (new profile file)" -ForegroundColor Green; $changedFiles++; continue }
    if (-not $newByFile.ContainsKey($name)) {
      Write-Host "`n- $name  removed (profile file gone)" -ForegroundColor Red; $changedFiles++; continue }

    $delta = @(Compare-Config $oldByFile[$name].config $newByFile[$name].config)
    if ($delta.Count -eq 0) { continue }
    $changedFiles++; $changes += $delta.Count
    Write-Host "`n~ $name  ($($delta.Count) change(s))" -ForegroundColor Yellow
    Write-Host ("    sha256 {0}  ->  {1}" -f $oldByFile[$name].sha256, $newByFile[$name].sha256) -ForegroundColor DarkGray
    Write-Host ("    mtime  {0}  ->  {1}" -f $oldByFile[$name].mtime,  $newByFile[$name].mtime)  -ForegroundColor DarkGray
    foreach ($d in $delta) {
      "    {0,-7} {1}" -f $d.Kind, $d.Path
      "              {0}  ->  {1}" -f $d.Old, $d.New
      if ($d.Path -match '\.button\.source_key$') {
        "              source_key: $(Show-Src $d.New)"
      }
    }
  }

  if ($changedFiles -eq 0) {
    Write-Host "`nNO CHANGE." -ForegroundColor Magenta
    Write-Host "Every path of every compared profile is equal -- not merely every" -ForegroundColor Magenta
    Write-Host "keyboardButton entry. If you just tried to remap a locked Fn key," -ForegroundColor Magenta
    Write-Host "that is the interesting result: AC did not record it locally." -ForegroundColor Magenta
  } else {
    Write-Host "`n$changes change(s) in $changedFiles file(s)." -ForegroundColor Green
  }
}

if ($Watch) {
  Write-Host "`nWatching for changes (Ctrl+C to stop)..." -ForegroundColor Green
  $last = @{}
  foreach ($p in $snap.profiles) { $last[$p.file] = $p.mtime }
  while ($true) {
    Start-Sleep -Milliseconds 400
    foreach ($f in Get-ProfileFiles) {
      $t = $f.LastWriteTimeUtc.ToString('o')
      if ($last[$f.Name] -ne $t) {
        $last[$f.Name] = $t
        Write-Host "[$(Get-Date -f HH:mm:ss)] $($f.Name) rewritten" -ForegroundColor Yellow
      }
    }
  }
}
