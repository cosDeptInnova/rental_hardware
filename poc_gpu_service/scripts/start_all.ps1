param(
  [switch]$RunSmokeTest = $false,
  [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".env")) {
  if (Test-Path ".env.example") {
    Copy-Item ".env.example" ".env"
    Write-Host "[start_all] .env created from .env.example"
  }
}

$env:PYTHONPATH = "."

Write-Host "[start_all] Starting gpu-agent on :8101"
$gpuAgentJob = Start-Job -ScriptBlock {
  param($wd)
  Set-Location $wd
  $env:PYTHONPATH = "."
  uvicorn apps.gpu_agent.main:app --host 0.0.0.0 --port 8101
} -ArgumentList (Get-Location).Path

Start-Sleep -Seconds 2

Write-Host "[start_all] Starting bastion-control-plane on :8000"
$bastionJob = Start-Job -ScriptBlock {
  param($wd)
  Set-Location $wd
  $env:PYTHONPATH = "."
  uvicorn apps.bastion_control_plane.main:app --host 0.0.0.0 --port 8000
} -ArgumentList (Get-Location).Path

Start-Sleep -Seconds 3
Write-Host "[start_all] Services started. Jobs:"
Get-Job | Format-Table Id, Name, State -AutoSize

Write-Host "\nHealth checks:"
try {
  Invoke-RestMethod -Uri "http://127.0.0.1:8101/health" -Headers @{"X-Internal-Token"="internal-secret-token"} | ConvertTo-Json -Depth 5
  Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" | ConvertTo-Json -Depth 5
}
catch {
  Write-Warning "Health check failed: $($_.Exception.Message)"
}

if ($RunSmokeTest) {
  Write-Host "\n[start_all] Running smoke test with GPU0 handoff flow..."
  & (Join-Path $PSScriptRoot "smoke_test.ps1")
}

Write-Host "\nTo stop all jobs in this shell: Get-Job | Stop-Job; Get-Job | Remove-Job"
