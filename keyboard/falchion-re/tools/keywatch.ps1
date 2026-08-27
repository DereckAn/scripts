<#
.SYNOPSIS
  Shows the actual virtual-key / scan code of whatever you press.

.DESCRIPTION
  Opens a small always-on-top window. Focus it and press keys; each keypress is logged with
  its virtual key code, scan code and name. Use this to tell "F1", "9" and "nothing" apart --
  in a text box all three can look identical.

  Press Esc to quit.
#>
Add-Type -AssemblyName System.Windows.Forms, System.Drawing

$f = New-Object Windows.Forms.Form
$f.Text = 'keywatch -- press keys (Esc to quit)'
$f.Size = New-Object Drawing.Size(560, 420)
$f.TopMost = $true
$f.KeyPreview = $true
$f.StartPosition = 'CenterScreen'

$box = New-Object Windows.Forms.TextBox
$box.Multiline = $true
$box.Dock = 'Fill'
$box.ScrollBars = 'Vertical'
$box.Font = New-Object Drawing.Font('Consolas', 11)
$box.ReadOnly = $true
$box.BackColor = [Drawing.Color]::Black
$box.ForeColor = [Drawing.Color]::Lime
$f.Controls.Add($box)

$log = {
  param($e)
  $vk = [int]$e.KeyCode
  $sc = ($e.KeyData -band 0xFF)
  $line = "vk=0x{0:X2} ({0,3})  {1,-14} mods:{2}" -f $vk, $e.KeyCode, $e.Modifiers
  $box.AppendText($line + "`r`n")
}

$f.Add_KeyDown({
  if ($_.KeyCode -eq 'Escape') { $f.Close(); return }
  & $log $_
  $_.SuppressKeyPress = $true
})

$box.AppendText("Focus this window and press Fn+1.`r`n")
$box.AppendText("  F1        -> vk=0x70 (112)`r`n")
$box.AppendText("  digit 9   -> vk=0x39 (57)`r`n")
$box.AppendText("  nothing   -> no line appears at all`r`n")
$box.AppendText(("-" * 52) + "`r`n")

[void]$f.ShowDialog()
