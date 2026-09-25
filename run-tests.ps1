# KnowledgePulse test runner (Windows PowerShell).
#
#   .\run-tests.ps1                     everything except live
#   .\run-tests.ps1 acceptance          one layer
#   .\run-tests.ps1 integration acceptance
#   .\run-tests.ps1 live                real models (API keys in backend\.env)
#
# Layers: frontend integration acceptance regression tenancy smoke live e2e all
# If scripts are blocked: powershell -ExecutionPolicy Bypass -File .\run-tests.ps1

param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Layers)

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Reports = Join-Path $Backend "test-reports"
$Generated = Join-Path $Backend "tests\suites\.generated"
$env:KP_REPORT_DIR = $Reports

if ($env:PYTHON) { $Py = $env:PYTHON }
elseif (Test-Path (Join-Path $Backend ".venv\Scripts\python.exe")) { $Py = Join-Path $Backend ".venv\Scripts\python.exe" }
else { $Py = "python" }

& $Py -c "import pytest" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "pytest is not installed for $Py. Run: pip install -r backend\requirements-dev.txt"; exit 2 }

if (-not $Layers -or $Layers.Count -eq 0 -or $Layers[0] -eq "all") { $Layers = @("frontend", "integration", "acceptance", "regression") }
New-Item -ItemType Directory -Force -Path $Reports | Out-Null
$Summary = @()
$Failed = $false

function Record($name, $code) {
  if ($code -eq 0) { $script:Summary += "  PASS  $name" } else { $script:Summary += "  FAIL  $name"; $script:Failed = $true }
}

function Export-Types {
  if ((Get-Command node -ErrorAction SilentlyContinue) -and (Test-Path (Join-Path $Frontend "node_modules\typescript"))) {
    New-Item -ItemType Directory -Force -Path $Generated | Out-Null
    node (Join-Path $Frontend "scripts\export-api-types.mjs") | Out-File -Encoding utf8 (Join-Path $Generated "frontend_types.json")
  }
}

function Run-Pytest($layer) {
  Write-Host "`n==== $layer ===================================================="
  Push-Location $Backend
  & $Py -m pytest -m $layer "--junitxml=$Reports\$layer-junit.xml"
  $code = $LASTEXITCODE
  Pop-Location
  Record $layer $code
}

foreach ($layer in $Layers) {
  switch ($layer) {
    "frontend" {
      Write-Host "`n==== frontend ================================================"
      if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { $Summary += "  SKIP  frontend"; continue }
      Push-Location $Frontend
      $code = 0
      if (-not (Test-Path "node_modules")) { npm ci --no-audit --no-fund; if ($LASTEXITCODE -ne 0) { $code = 1 } }
      if ($code -eq 0) { Write-Host "-- type check"; npx tsc --noEmit; if ($LASTEXITCODE -ne 0) { $code = 1 } }
      if ($code -eq 0) { Write-Host "-- build"; npm run build; if ($LASTEXITCODE -ne 0) { $code = 1 } }
      Pop-Location
      if ($code -eq 0) { Export-Types }
      Record "frontend" $code
    }
    "integration" { Export-Types; Run-Pytest "integration" }
    "acceptance" { Run-Pytest "acceptance" }
    "regression" { Run-Pytest "regression" }
    "live" {
      Write-Host "`n==== live (real models, uses backend\.env) ===================="
      Push-Location $Backend
      $env:KP_LIVE = "1"
      & $Py -m pytest -m live -s "--junitxml=$Reports\live-junit.xml"
      $code = $LASTEXITCODE
      Remove-Item Env:KP_LIVE
      Pop-Location
      Record "live" $code
    }
    "e2e" {
      Write-Host "`n==== e2e (browser) ============================================"
      Push-Location $Backend; & $Py tests/e2e/run_e2e.py; $code = $LASTEXITCODE; Pop-Location
      Record "e2e" $code
    }
    "tenancy" {
      Write-Host "`n==== tenancy (standalone unittest) ==========================="
      Push-Location $Backend; & $Py -m unittest tests/test_multitenancy.py; $code = $LASTEXITCODE; Pop-Location
      Record "tenancy" $code
    }
    "smoke" {
      Write-Host "`n==== smoke ===================================================="
      Push-Location $Backend; & $Py scripts/smoke_test.py; $code = $LASTEXITCODE; Pop-Location
      Record "smoke" $code
    }
    default { Write-Host "Unknown layer: $layer"; exit 2 }
  }
}

Write-Host "`n==== summary ================================================="
$Summary | ForEach-Object { Write-Host $_ }
Write-Host "Reports: $Reports"
if (Test-Path (Join-Path $Reports "traceability.md")) { Write-Host "Traceability: $Reports\traceability.md" }
if ($Failed) { exit 1 } else { exit 0 }
