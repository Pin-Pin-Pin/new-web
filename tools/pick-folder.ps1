param(
  [Parameter(Mandatory = $true)]
  [string]$StartDir,

  [Parameter(Mandatory = $true)]
  [string]$OutFile
)

$ErrorActionPreference = 'Stop'

if (Test-Path -LiteralPath $OutFile) {
  Remove-Item -LiteralPath $OutFile -Force
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
# Start at merge.bat dir; user must navigate into the actual page folder
$dialog.Description = 'Start here, then open the page folder (e.g. general-donate). Do not pick the repo root.'
$dialog.ShowNewFolderButton = $false
$dialog.RootFolder = [System.Environment+SpecialFolder]::MyComputer

if (-not [string]::IsNullOrWhiteSpace($StartDir) -and (Test-Path -LiteralPath $StartDir)) {
  $dialog.SelectedPath = (Resolve-Path -LiteralPath $StartDir).Path
}

# Ensure WinForms message loop works when launched from cmd
[System.Windows.Forms.Application]::EnableVisualStyles() | Out-Null

$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK -and -not [string]::IsNullOrWhiteSpace($dialog.SelectedPath)) {
  # UTF-8 without BOM so cmd set /p can read the path
  $utf8NoBom = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllText($OutFile, $dialog.SelectedPath.Trim(), $utf8NoBom)
  exit 0
}

exit 1
