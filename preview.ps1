# preview.ps1 - the site, live, at http://localhost:8000
# Mirrors .github/workflows/main.yml, but takes the PDFs from the working tree, so uncommitted changes
# show up too. It keeps itself up to date: newly APPROVED notes are pulled into the site
# (website/sync_pdfs.py; drafts never are), and when anything changes (notes, PDFs, website files)
# the site is rebuilt and the open page reloads by itself. Ctrl+C stops it.
# Usage: .\preview.ps1 [-Port 8000] [-NoOpen] [-Once]   (-Once: build and serve, no watching)
param([int]$Port = 8000, [switch]$NoOpen, [switch]$Once)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
Set-Location $root
$out = Join-Path $root 'out'

# jsdom lives outside the repo (nothing to commit, survives across runs)
$deps = Join-Path $env:LOCALAPPDATA 'summaries-preview'
if (-not (Test-Path (Join-Path $deps 'node_modules\jsdom'))) {
    Write-Host 'Installing jsdom (first run only)...'
    New-Item -ItemType Directory -Force $deps | Out-Null
    npm install --prefix $deps jsdom --no-audit --no-fund --silent
    if ($LASTEXITCODE -ne 0) { throw 'npm install jsdom failed' }
}
$env:NODE_PATH = Join-Path $deps 'node_modules'

# PDFs open in a pdf.js viewer page (preview only; the deployed site is untouched), so they show even
# in browsers without a PDF viewer (the Claude app's browser pane); both pages reload after a rebuild
$hook = @'
<script>
document.addEventListener('DOMContentLoaded', () => {
  for (const a of document.querySelectorAll('a[href$=".pdf"]')) {
    if (/^https?:/.test(a.getAttribute('href'))) continue;
    a.href = 'viewer.html?file=' + encodeURIComponent(a.getAttribute('href'));
    a.removeAttribute('target');
  }
});
let builtAt = null;
setInterval(async () => {
  try {
    const v = await (await fetch('version.txt', { cache: 'no-store' })).text();
    if (builtAt && v !== builtAt) location.reload();
    builtAt = v;
  } catch (e) {}
}, 2000);
</script>
'@

function Build-Site {
    # 1. approved notes -> the site's PDFs (drafts are skipped and the site keeps the older copy)
    py -X utf8 website/sync_pdfs.py | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Host 'sync_pdfs.py failed; building with the PDFs as they are' -ForegroundColor Yellow }
    # 2. the page (builder.js recreates ./out)
    node website/builder.js | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Host 'builder.js failed' -ForegroundColor Red; return }
    foreach ($f in 'main.css', 'main.js', 'favicon.ico') { Copy-Item "website\$f" $out }
    Copy-Item website\icon (Join-Path $out 'icon') -Recurse
    # 3. every PDF in the working tree, at the same relative path
    $n = 0
    Get-ChildItem $root -Recurse -Filter *.pdf -File | Where-Object { -not $_.FullName.StartsWith($out + '\') } | ForEach-Object {
        $dst = Join-Path $out $_.FullName.Substring($root.Length + 1)
        New-Item -ItemType Directory -Force (Split-Path $dst) | Out-Null
        Copy-Item $_.FullName $dst
        $n++
    }
    Copy-Item preview_viewer.html (Join-Path $out 'viewer.html')
    $index = Join-Path $out 'index.html'
    $html = [IO.File]::ReadAllText($index).Replace('</body>', "$hook</body>")
    [IO.File]::WriteAllText($index, $html, (New-Object Text.UTF8Encoding $false))
    [IO.File]::WriteAllText((Join-Path $out 'version.txt'), (Get-Date).Ticks.ToString())
    Write-Host ("[{0:HH:mm:ss}] built: {1} PDFs" -f (Get-Date), $n)
}

# what is watched: the website files, the repo's PDFs, and every notes PDF the site takes from outside
function Get-Stamp {
    $files = @(Get-ChildItem (Join-Path $root 'website') -File) + @(Get-ChildItem (Join-Path $root 'summaries') -Recurse -File)
    try {
        $data = Get-Content (Join-Path $root 'website\pdf_data.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($p in $data.PSObject.Properties) {
            $e = $p.Value
            $srcs = @()
            if ($e.URL_from) { $srcs += $e.URL_from }
            if ($e.by_lecture -and $e.by_lecture.pdfs) { $srcs += @($e.by_lecture.pdfs | ForEach-Object { $_.from }) }
            if ($e.by_lecture -and $e.by_lecture.parts) { $srcs += $e.by_lecture.parts }
            foreach ($s in $srcs) { if ($s -and (Test-Path $s)) { $files += Get-Item $s } }
        }
    } catch {}
    ($files | Where-Object { $_.FullName -notmatch '\\by_lecture\\' } | ForEach-Object { $_.LastWriteTimeUtc.Ticks } | Measure-Object -Maximum).Maximum
}

Build-Site
$url = "http://localhost:$Port/"
$server = Start-Process py -ArgumentList '-m', 'http.server', $Port, '--bind', '127.0.0.1', '--directory', "`"$out`"" -NoNewWindow -PassThru
Write-Host "Serving $url  (Ctrl+C to stop)$(if (-not $Once) { '; watching for changes' })"
if (-not $NoOpen) { Start-Process $url }
try {
    if ($Once) { $server.WaitForExit(); return }
    $stamp = Get-Stamp
    while (-not $server.HasExited) {
        Start-Sleep -Seconds 3
        if ((Get-Stamp) -ne $stamp) {
            Start-Sleep -Seconds 2   # let a writer finish (LaTeX writes the PDF in steps)
            Build-Site
            $stamp = Get-Stamp       # the build itself rewrites some files
        }
    }
} finally {
    if (-not $server.HasExited) { Stop-Process -Id $server.Id -Force }
}
