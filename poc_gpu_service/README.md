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

## Arranque
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

## PowerShell: snapshot GPU0
```powershell
$h = @{"X-API-Key"="client1_key_123"}
Invoke-RestMethod -Headers $h -Method Post -ContentType "application/json" -Uri "http://127.0.0.1:8000/v1/admin/gpu0/snapshot" -Body '{"lease_id":"lease-123","tenant_id":"cliente1"}'
```

## PowerShell: release GPU0
```powershell
$h = @{"X-API-Key"="client1_key_123"}
Invoke-RestMethod -Headers $h -Method Post -ContentType "application/json" -Uri "http://127.0.0.1:8000/v1/admin/gpu0/release" -Body '{"lease_id":"lease-123","tenant_id":"cliente1","target_free_vram_mib":16000,"safety_margin_mib":2048,"dry_run":true}'
```

## PowerShell: crear lease cliente con handoff
```powershell
$h = @{"X-API-Key"="client1_key_123"}
Invoke-RestMethod -Headers $h -Method Post -ContentType "application/json" -Uri "http://127.0.0.1:8000/v1/leases" -Body '{"model_alias":"llama3-8b-instruct","task_type":"chat","requested_gpu":"CUDA0"}'
```

## PowerShell: cerrar lease y restaurar
```powershell
$h = @{"X-API-Key"="client1_key_123"}
Invoke-RestMethod -Headers $h -Method Post -ContentType "application/json" -Uri "http://127.0.0.1:8000/v1/leases/close" -Body '{"lease_id":"lease-123"}'
```

## Ejemplos API (curl)
```bash
curl -H "X-API-Key: client1_key_123" http://127.0.0.1:8000/v1/catalog
curl -X POST -H "X-API-Key: client1_key_123" -H "Content-Type: application/json" -d '{"model_alias":"llama3-8b-instruct"}' http://127.0.0.1:8000/v1/models/ensure
curl -X POST -H "X-API-Key: client1_key_123" -H "Content-Type: application/json" -d '{"model_alias":"llama3-8b-instruct","task_type":"chat"}' http://127.0.0.1:8000/v1/leases
curl -X POST -H "X-API-Key: client1_key_123" -H "Content-Type: application/json" -d '{"lease_id":"<LEASE_ID>","messages":[{"role":"user","content":"Hola"}]}' http://127.0.0.1:8000/v1/chat/completions
curl -H "X-API-Key: client1_key_123" http://127.0.0.1:8000/v1/usage/summary
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
- Si el catálogo no trae enough metadata de procesos externos, mantener allow-list manual y flujo semiautomático de aprobación antes de drenar.
