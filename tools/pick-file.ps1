param(
  [Parameter(Mandatory = $true)]
  [string]$StartDir,

  [Parameter(Mandatory = $true)]
  [string]$OutFile,

  [string]$Filter = 'CSS files (*.css)|*.css|All files (*.*)|*.*'
)

$ErrorActionPreference = 'Stop'

if (Test-Path -LiteralPath $OutFile) {
  Remove-Item -LiteralPath $OutFile -Force
}

Add-Type -AssemblyName System.Windows.Forms

$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = 'Select a CSS file'
$dialog.Filter = $Filter
$dialog.Multiselect = $false
$dialog.CheckFileExists = $true

if (-not [string]::IsNullOrWhiteSpace($StartDir) -and (Test-Path -LiteralPath $StartDir)) {
  $dialog.InitialDirectory = (Resolve-Path -LiteralPath $StartDir).Path
}

[System.Windows.Forms.Application]::EnableVisualStyles() | Out-Null

$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK -and -not [string]::IsNullOrWhiteSpace($dialog.FileName)) {
  $utf8NoBom = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllText($OutFile, $dialog.FileName.Trim(), $utf8NoBom)
  exit 0
}

exit 1
