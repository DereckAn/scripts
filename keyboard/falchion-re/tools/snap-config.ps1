<#
.SYNOPSIS
  Decodes the Armoury Crate on-disk profile for the Falchion Ace HFX, and diffs snapshots.

.DESCRIPTION
  AC stores the whole keyboard config as base64( percent-encode( JSON ) ) inside an XML
  wrapper. This decodes it to plain JSON and, given a previous snapshot, prints exactly
  which keyfunction entries changed.

  Workflow:
    1) .\snap-config.ps1 -Save before.json
    2) change ONE thing in Armoury Crate, hit Apply
    3) .\snap-config.ps1 -Save after.json -Diff before.json

  The entry that changed IS that key's matrix coordinate. See notes/key-matrix.md.

  Read-only with respect to the keyboard -- this only reads files AC already wrote.

.EXAMPLE
  .\snap-config.ps1 -Save before.json
  .\snap-config.ps1 -Save after.json -Diff before.json
#>
[CmdletBinding()]
param(
  [string]$Profile = '3',
  [string]$Model   = '024080600167',
  [string]$Save,
  [string]$Diff,
  [switch]$Watch
)

$ErrorActionPreference = 'Stop'
$dir = "C:\ProgramData\ASUS\Framework\keyboard\ROG FALCHION ACE HFX"
$src = Join-Path $dir "fp_${Profile}_config_${Model}.xml"
if (-not (Test-Path $src)) {
  Write-Host "Not found: $src" -ForegroundColor Red
  Write-Host "Available:" -ForegroundColor Yellow
  Get-ChildItem $dir -Filter *.xml -ErrorAction SilentlyContinue | ForEach-Object { "  $($_.Name)" }
  exit 1
}

function Get-Config($path) {
  $b64 = ([xml](Get-Content $path -Raw)).root.device_type.device.function.file_data
  $txt = [uri]::UnescapeDataString([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64)))
  $txt | ConvertFrom-Json
}

function Get-Flat($cfg) {
  $h = @{}
  foreach ($p in $cfg.button.keyboardButton.PSObject.Properties) {
    $v = $p.Value
    $h[$p.Name] = [pscustomobject]@{
      mode   = "$($v.selectedmode)"
      defKey = "$($v.defaultKey)"
      src    = "$($v.button.source_key)"
      bfun   = "$($v.button.normal.button_function)"
      tgt    = "$($v.button.normal.target_key)"
      act    = "$($v.button.normal.actuation)"
      trig   = "$($v.button.trigger_type)"
      kd     = "$($v.keydata_1)/$($v.keydata_2)/$($v.keydata_3)"
    }
  }
  $h
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

$cfg = Get-Config $src
$cur = Get-Flat $cfg
Write-Host "source : $src" -ForegroundColor Cyan
Write-Host "mtime  : $((Get-Item $src).LastWriteTime)" -ForegroundColor Cyan
Write-Host "entries: $($cur.Count)" -ForegroundColor Cyan

if ($Save) {
  $cfg | ConvertTo-Json -Depth 25 | Out-File $Save -Encoding utf8
  Write-Host "saved  : $Save" -ForegroundColor Green
}

if ($Diff) {
  if (-not (Test-Path $Diff)) { Write-Host "baseline not found: $Diff" -ForegroundColor Red; exit 1 }
  $old = Get-Flat (Get-Content $Diff -Raw | ConvertFrom-Json)

  $changed = 0
  foreach ($k in ($cur.Keys | Sort-Object)) {
    if (-not $old.ContainsKey($k)) { Write-Host "+ $k (new)" -ForegroundColor Green; $changed++; continue }
    $a = $old[$k]; $b = $cur[$k]
    $fields = $a.PSObject.Properties.Name | Where-Object { $a.$_ -ne $b.$_ }
    if ($fields) {
      $changed++
      Write-Host "`n~ $k" -ForegroundColor Yellow
      Write-Host "    source_key: $(Show-Src $b.src)" -ForegroundColor DarkGray
      foreach ($f in $fields) { "    {0,-7} {1}  ->  {2}" -f $f, $a.$f, $b.$f }
    }
  }
  foreach ($k in ($old.Keys | Sort-Object)) {
    if (-not $cur.ContainsKey($k)) { Write-Host "- $k (removed)" -ForegroundColor Red; $changed++ }
  }

  if ($changed -eq 0) {
    Write-Host "`nNO CHANGE." -ForegroundColor Magenta
    Write-Host "If you just tried to remap a locked Fn key, that is the interesting result:" -ForegroundColor Magenta
    Write-Host "AC did not even record the change locally -> the lock is client-side." -ForegroundColor Magenta
  } else {
    Write-Host "`n$changed entr$(if($changed -eq 1){'y'}else{'ies'}) changed." -ForegroundColor Green
  }
}

if ($Watch) {
  Write-Host "`nWatching for changes (Ctrl+C to stop)..." -ForegroundColor Green
  $last = (Get-Item $src).LastWriteTime
  while ($true) {
    Start-Sleep -Milliseconds 400
    $t = (Get-Item $src).LastWriteTime
    if ($t -ne $last) { $last = $t; Write-Host "[$(Get-Date -f HH:mm:ss)] config rewritten" -ForegroundColor Yellow }
  }
}
