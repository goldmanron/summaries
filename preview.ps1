# preview.ps1 - build the site locally and serve it at http://localhost:8000
# Mirrors .github/workflows/main.yml, but takes the PDFs from the working tree,
# so uncommitted changes show up too. Usage: .\preview.ps1 [-Port 8000] [-NoOpen]
param([int]$Port = 8000, [switch]$NoOpen)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
Set-Location $root

# jsdom lives outside the repo (nothing to commit, survives across runs)
$deps = Join-Path $env:LOCALAPPDATA 'summaries-preview'
if (-not (Test-Path (Join-Path $deps 'node_modules\jsdom'))) {
    Write-Host 'Installing jsdom (first run only)...'
    New-Item -ItemType Directory -Force $deps | Out-Null
    npm install --prefix $deps jsdom --no-audit --no-fund --silent
    if ($LASTEXITCODE -ne 0) { throw 'npm install jsdom failed' }
}
$env:NODE_PATH = Join-Path $deps 'node_modules'

# build (writes ./out/index.html)
node website/builder.js
if ($LASTEXITCODE -ne 0) { throw 'builder.js failed' }

# static files, as in the deploy workflow
$out = Join-Path $root 'out'
foreach ($f in 'main.css', 'main.js', 'favicon.ico') { Copy-Item "website\$f" $out }
Copy-Item website\icon (Join-Path $out 'icon') -Recurse

# every PDF in the working tree, at the same relative path
$n = 0
Get-ChildItem $root -Recurse -Filter *.pdf -File |
    Where-Object { -not $_.FullName.StartsWith($out + '\') } |
    ForEach-Object {
        $rel = $_.FullName.Substring($root.Length + 1)
        $dst = Join-Path $out $rel
        New-Item -ItemType Directory -Force (Split-Path $dst) | Out-Null
        Copy-Item $_.FullName $dst
        $n++
    }
Write-Host "Copied $n PDFs."

# PDFs open in a pdf.js viewer page (preview only; the deployed site is untouched),
# so they show even in browsers without a PDF viewer, e.g. the Claude app's browser pane
Copy-Item preview_viewer.html (Join-Path $out 'viewer.html')
$hook = @'
<script>
document.addEventListener('DOMContentLoaded', () => {
  for (const a of document.querySelectorAll('a[href$=".pdf"]')) {
    if (/^https?:/.test(a.getAttribute('href'))) continue;
    a.href = 'viewer.html?file=' + encodeURIComponent(a.getAttribute('href'));
    a.removeAttribute('target');
  }
});
</script>
'@
$index = Join-Path $out 'index.html'
$html = [IO.File]::ReadAllText($index).Replace('</body>', "$hook</body>")
[IO.File]::WriteAllText($index, $html, (New-Object Text.UTF8Encoding $false))

$url = "http://localhost:$Port/"
Write-Host "Serving $url  (Ctrl+C to stop)"
if (-not $NoOpen) { Start-Process $url }
py -m http.server $Port --bind 127.0.0.1 --directory $out
