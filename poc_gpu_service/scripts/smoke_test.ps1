param(
  [string]$BaseUrl = "http://127.0.0.1:8000",
  [string]$ApiKey = "client1_key_123",
  [string]$ModelAlias = "llama3-8b-instruct",
  [switch]$DryRunRelease = $true,
  [switch]$DryRunRestore = $true
)

$ErrorActionPreference = "Stop"
$headers = @{
  "X-API-Key" = $ApiKey
  "X-Request-Id" = "smoke-$([guid]::NewGuid().ToString())"
}

function Invoke-Step {
  param(
    [string]$Title,
    [scriptblock]$Action
  )
  Write-Host "\n=== $Title ==="
  $result = & $Action
  $result | ConvertTo-Json -Depth 10
  return $result
}

# 1) catalog
$catalog = Invoke-Step "Catalog" {
  Invoke-RestMethod -Headers $headers -Uri "$BaseUrl/v1/catalog"
}

# 2) ensure_model
$ensure = Invoke-Step "Ensure model" {
  Invoke-RestMethod -Headers $headers -Method Post -ContentType "application/json" -Uri "$BaseUrl/v1/models/ensure" -Body (@{model_alias=$ModelAlias} | ConvertTo-Json)
}

# 3) release gpu0
$releaseBody = @{
  tenant_id = "cliente1"
  target_free_vram_mib = 16000
  safety_margin_mib = 2048
  dry_run = [bool]$DryRunRelease
}
$release = Invoke-Step "Release GPU0 capacity" {
  Invoke-RestMethod -Headers $headers -Method Post -ContentType "application/json" -Uri "$BaseUrl/v1/admin/gpu0/release" -Body ($releaseBody | ConvertTo-Json)
}

# 4) create lease
$lease = Invoke-Step "Create lease" {
  Invoke-RestMethod -Headers $headers -Method Post -ContentType "application/json" -Uri "$BaseUrl/v1/leases" -Body (@{model_alias=$ModelAlias; task_type="chat"; requested_gpu="CUDA0"} | ConvertTo-Json)
}
$leaseId = $lease.lease_id
if (-not $leaseId) { throw "Lease creation failed: lease_id missing" }

# 5) chat completion
$chat = Invoke-Step "Chat completion" {
  Invoke-RestMethod -Headers $headers -Method Post -ContentType "application/json" -Uri "$BaseUrl/v1/chat/completions" -Body (@{lease_id=$leaseId; messages=@(@{role="user";content="Hola, responde con OK"})} | ConvertTo-Json -Depth 10)
}

# 6) close lease
$close = Invoke-Step "Close lease" {
  Invoke-RestMethod -Headers $headers -Method Post -ContentType "application/json" -Uri "$BaseUrl/v1/leases/close" -Body (@{lease_id=$leaseId} | ConvertTo-Json)
}

# 7) restore gpu0 (manual admin path)
$restoreBody = @{
  lease_id = $leaseId
  dry_run = [bool]$DryRunRestore
}
$restore = Invoke-Step "Restore GPU0" {
  Invoke-RestMethod -Headers $headers -Method Post -ContentType "application/json" -Uri "$BaseUrl/v1/admin/gpu0/restore" -Body ($restoreBody | ConvertTo-Json)
}

Write-Host "\nSmoke flow completed."
