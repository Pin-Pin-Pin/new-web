# Insert fix-b.css at the start of the first <style>, write *_merge.html
$ErrorActionPreference = 'Stop'
$dir = $PSScriptRoot
$cssPath = Join-Path $dir 'fix-b.css'
if (-not (Test-Path $cssPath)) {
    Write-Host '[ERROR] fix-b.css not found'
    exit 1
}

$css = [System.IO.File]::ReadAllText($cssPath).TrimEnd()
$cssBlock = "/* fix-b.css */`r`n$css`r`n"
$utf8 = New-Object System.Text.UTF8Encoding $false
$count = 0

Get-ChildItem -Path $dir -Filter '*.html' -File |
    Where-Object { $_.BaseName -notmatch '_merge$' } |
    ForEach-Object {
        $html = [System.IO.File]::ReadAllText($_.FullName)

        $html = [regex]::Replace(
            $html,
            '(?is)<link\s+rel\s*=\s*["'']stylesheet["'']\s+href\s*=\s*["'']fix-b\.css["'']\s*/?\s*>\s*',
            ''
        )

        $script:insertOnce = $true
        $html2 = [regex]::Replace(
            $html,
            '(?is)(<style\b[^>]*>)',
            {
                param($m)
                if (-not $script:insertOnce) { return $m.Value }
                $script:insertOnce = $false
                return $m.Value + "`r`n" + $cssBlock
            },
            1
        )

        if ($script:insertOnce) {
            $styleTag = "<style type=`"text/css`">`r`n$cssBlock</style>`r`n"
            if ($html2 -match '(?i)</head>') {
                $html2 = [regex]::Replace($html2, '(?i)</head>', ($styleTag + '</head>'), 1)
            }
            else {
                $html2 = $styleTag + $html2
            }
        }

        $out = Join-Path $dir ($_.BaseName + '_merge.html')
        [System.IO.File]::WriteAllText($out, $html2, $utf8)
        Write-Host ("  {0} -> {1}" -f $_.Name, (Split-Path $out -Leaf))
        $count++
    }

Write-Host ("Done: {0} file(s)." -f $count)
