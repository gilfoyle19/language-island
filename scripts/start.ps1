[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$env:UV_CACHE_DIR = Join-Path $ProjectRoot ".uv-cache"
$ApiProcess = $null

Set-Location $ProjectRoot

try {
    Write-Host "Synchronizing the locked uv environment..."
    & uv sync --locked --all-groups
    if ($LASTEXITCODE -ne 0) {
        throw "uv sync failed with exit code $LASTEXITCODE"
    }

    Write-Host "Starting FastAPI on http://127.0.0.1:8000..."
    $ApiProcess = Start-Process `
        -FilePath "uv" `
        -ArgumentList @("run", "--locked", "uvicorn", "language_island.api.app:app", "--host", "127.0.0.1", "--port", "8000") `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -PassThru

    $Ready = $false
    for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
        if ($ApiProcess.HasExited) {
            throw "FastAPI exited before becoming ready."
        }
        try {
            $null = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 1
            $Ready = $true
            break
        }
        catch {
            Start-Sleep -Milliseconds 250
        }
    }

    if (-not $Ready) {
        throw "FastAPI did not become ready within the expected time."
    }

    Write-Host "Starting Streamlit on http://127.0.0.1:8501..."
    & uv run --locked streamlit run src/language_island/ui/app.py --server.address 127.0.0.1 --server.port 8501
}
finally {
    if (($null -ne $ApiProcess) -and (-not $ApiProcess.HasExited)) {
        Stop-Process -Id $ApiProcess.Id -Force
    }
}
