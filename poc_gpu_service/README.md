# PoC Inference as a Service / GPU as a Service (Windows)

PoC con dos servicios FastAPI:
- `bastion-control-plane` (público para cliente)
- `gpu-agent` (privado, sólo bastión vía token interno)

## Estructura
```text
poc_gpu_service/
  apps/bastion_control_plane
  apps/gpu_agent
  shared/
  scripts/
  catalog/models.json
  state/
```

## Requisitos
- Python 3.11+
- Windows Server / Windows 10+
- NVIDIA driver + `nvidia-smi` en PATH

## Instalación (PowerShell)
```powershell
cd poc_gpu_service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

## Configuración de handoff GPU0
Variables nuevas:
- `ENABLE_GPU0_HANDOFF=true/false`
- `CLIENT_GPU0_TARGET_FREE_VRAM_MIB`
- `CLIENT_GPU0_SAFETY_MARGIN_MIB`
- `CLIENT_GPU0_DRAIN_TIMEOUT_SECONDS`
- `CLIENT_GPU0_RESTORE_ON_DISCONNECT=true/false`
- `DRAINABLE_BACKEND_TAGS=production_replicas,internal_non_critical`
- `NON_DRAINABLE_PROCESS_PATTERNS=nvidia|system|display|dwm`

## Arranque rápido
### Opción A: manual
Terminal 1:
```powershell
$env:PYTHONPATH='.'
uvicorn apps.gpu_agent.main:app --host 0.0.0.0 --port 8101
```

Terminal 2:
```powershell
$env:PYTHONPATH='.'
uvicorn apps.bastion_control_plane.main:app --host 0.0.0.0 --port 8000
```

### Opción B: script
```powershell
./scripts/start_all.ps1
# o:
./scripts/start_all.ps1 -RunSmokeTest
```

## Scripts internos allow-listed
```powershell
python scripts\inventory_models.py
python scripts\ensure_model.py --model_alias llama3-8b-instruct
python scripts\start_backend.py --model_alias llama3-8b-instruct --tenant_id cliente1 --gpu_device CUDA0
python scripts\stop_backend.py --instance_id <instance_id>
python scripts\collect_gpu_metrics.py
python scripts\snapshot_gpu0_state.py --lease_id lease-123 --tenant_id cliente1
python scripts\release_gpu0_capacity.py --lease_id lease-123 --tenant_id cliente1 --target_free_vram_mib 16000 --safety_margin_mib 2048 --dry_run
python scripts\restore_gpu0_state.py --lease_id lease-123 --dry_run
```

## Endpoints nuevos
Bastion:
- `POST /v1/admin/gpu0/snapshot`
- `POST /v1/admin/gpu0/release`
- `POST /v1/admin/gpu0/restore`
- `GET /v1/admin/gpu0/status`
- `GET /v1/admin/gpu0/snapshots`
- `GET /v1/admin/gpu0/handoff-events`
- `GET /v1/demo/status`
- `POST /v1/leases/close`

GPU Agent:
- `GET /internal/gpu/0/status`
- `POST /internal/gpu/0/snapshot`
- `POST /internal/gpu/0/release`
- `POST /internal/gpu/0/restore`
- `GET /internal/gpu/0/snapshots`
- `GET /internal/gpu/0/handoff-events`

## Invoke-RestMethod: flujo completo de demo
```powershell
$base = "http://127.0.0.1:8000"
$h = @{
  "X-API-Key" = "client1_key_123"
  "X-Request-Id" = "demo-$([guid]::NewGuid().ToString())"
}

# 1) catalog
$catalog = Invoke-RestMethod -Headers $h -Uri "$base/v1/catalog"

# 2) ensure_model
$ensure = Invoke-RestMethod -Headers $h -Method Post -ContentType "application/json" -Uri "$base/v1/models/ensure" -Body '{"model_alias":"llama3-8b-instruct"}'

# 3) release gpu0
$release = Invoke-RestMethod -Headers $h -Method Post -ContentType "application/json" -Uri "$base/v1/admin/gpu0/release" -Body '{"tenant_id":"cliente1","target_free_vram_mib":16000,"safety_margin_mib":2048,"dry_run":true}'

# 4) create lease
$lease = Invoke-RestMethod -Headers $h -Method Post -ContentType "application/json" -Uri "$base/v1/leases" -Body '{"model_alias":"llama3-8b-instruct","task_type":"chat","requested_gpu":"CUDA0"}'
$leaseId = $lease.lease_id

# 5) chat completion
$chatBody = @{lease_id=$leaseId;messages=@(@{role="user";content="Hola, responde con OK"})} | ConvertTo-Json -Depth 6
$chat = Invoke-RestMethod -Headers $h -Method Post -ContentType "application/json" -Uri "$base/v1/chat/completions" -Body $chatBody

# 6) close lease
$close = Invoke-RestMethod -Headers $h -Method Post -ContentType "application/json" -Uri "$base/v1/leases/close" -Body (@{lease_id=$leaseId} | ConvertTo-Json)

# 7) restore gpu0
$restore = Invoke-RestMethod -Headers $h -Method Post -ContentType "application/json" -Uri "$base/v1/admin/gpu0/restore" -Body (@{lease_id=$leaseId;dry_run=$true} | ConvertTo-Json)
```

También puedes correrlo empaquetado:
```powershell
./scripts/smoke_test.ps1
```

## Demo paso a paso en 10 minutos
1. Copia entorno e instala dependencias.
2. Arranca servicios con `./scripts/start_all.ps1`.
3. Verifica salud:
   - `http://127.0.0.1:8101/health`
   - `http://127.0.0.1:8000/health`
4. Consulta catálogo y asegura el modelo.
5. Ejecuta release GPU0 en `dry_run=true` y revisa `target_reached`.
6. Crea lease cliente en `CUDA0`.
7. Lanza una petición chat.
8. Consulta `GET /v1/demo/status` para ver:
   - free/used/reserved GPU0
   - leases activos
   - último snapshot
   - últimas acciones de release/restore
9. Cierra lease con `/v1/leases/close`.
10. Ejecuta restore manual (si deseas) y revisa `/v1/admin/gpu0/handoff-events`.

> Seed demo incluida:
> - tenants: `interno`, `cliente1`
> - api keys: `internal_key_456`, `client1_key_123`
> - backend interno drainable en GPU0: `seed-internal-drainable-gpu0`
> - backend interno crítico no drenable en GPU0: `seed-internal-critical-gpu0`

## Ejemplos API (curl)
```bash
curl -H "X-API-Key: client1_key_123" http://127.0.0.1:8000/v1/catalog
curl -X POST -H "X-API-Key: client1_key_123" -H "Content-Type: application/json" -d '{"model_alias":"llama3-8b-instruct"}' http://127.0.0.1:8000/v1/models/ensure
curl -X POST -H "X-API-Key: client1_key_123" -H "Content-Type: application/json" -d '{"model_alias":"llama3-8b-instruct","task_type":"chat"}' http://127.0.0.1:8000/v1/leases
```

## Ejecutar tests
```powershell
$env:PYTHONPATH='.'
pytest -q
```

## Notas de producción futura
- Cambiar SQLite por PostgreSQL.
- Reemplazar rate-limit en memoria por Redis.
- Ejecutar servicios con NSSM/WinSW.
- Endurecer tokenización/costing y concurrencia multi-tenant.
- Mantener allow-list manual y aprobación previa si hay procesos no catalogados.
