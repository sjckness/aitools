# sjck installer for Windows (PowerShell) — no clone needed.
#   irm https://raw.githubusercontent.com/sjckness/sjckAI-tools/main/get.ps1 | iex
# Pin a release: $env:SJCK_REF = "v0.4.0" before running. Skip parts: $env:SJCK_SETUP_ARGS = "--no-vscode"
$ErrorActionPreference = 'Stop'

$repo = if ($env:SJCK_REPO) { $env:SJCK_REPO } else { 'sjckness/sjckAI-tools' }
$ref  = if ($env:SJCK_REF)  { $env:SJCK_REF }  else { 'latest' }
$url  = if ($ref -eq 'latest') { "https://github.com/$repo/releases/latest/download/sjck-console.tgz" }
        else { "https://github.com/$repo/releases/download/$ref/sjck-console.tgz" }

function Fail($msg) { Write-Host "x $msg" -ForegroundColor Red; exit 1 }

Write-Host 'sjck installer' -ForegroundColor Cyan

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  Fail 'Node.js 20+ is required: https://nodejs.org  (or: winget install OpenJS.NodeJS.LTS)'
}
$major = [int](node -p "process.versions.node.split('.')[0]")
if ($major -lt 20) { Fail "Node.js $major found, 20+ is required" }

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
  Write-Host '-> Claude Code not found, installing it with npm'
  npm i -g '@anthropic-ai/claude-code'
  if ($LASTEXITCODE -ne 0) { Fail 'could not install Claude Code; see https://code.claude.com' }
  Write-Host '   run `claude` once to log in, then run this installer again if plugins fail'
}

Write-Host "-> sjck console ($ref)"
npm i -g $url 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host '   no release package found, building from source'
  $src = if ($ref -eq 'latest') { 'main' } else { $ref }
  $tmp = Join-Path ([IO.Path]::GetTempPath()) ("sjck-" + [guid]::NewGuid())
  New-Item -ItemType Directory $tmp | Out-Null
  Invoke-WebRequest "https://codeload.github.com/$repo/zip/$src" -OutFile "$tmp\src.zip"
  Expand-Archive "$tmp\src.zip" $tmp
  $root = Get-ChildItem $tmp -Directory | Select-Object -First 1
  Push-Location "$($root.FullName)\console"; npm pack --silent | Out-Null; Pop-Location
  $pkg = Get-ChildItem "$($root.FullName)\console\sjck-*.tgz" | Select-Object -First 1
  npm i -g $pkg.FullName
  if ($LASTEXITCODE -ne 0) { Fail 'console install failed' }
  Remove-Item -Recurse -Force $tmp
}

# npm's global folder may not be on PATH in this session yet
$env:Path = "$(npm prefix -g);$env:Path"
$setupArgs = if ($env:SJCK_SETUP_ARGS) { $env:SJCK_SETUP_ARGS -split ' ' } else { @() }
sjck setup @setupArgs
