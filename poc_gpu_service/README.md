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
```

## Ejemplos API (curl)
```bash
curl -H "X-API-Key: client1_key_123" http://127.0.0.1:8000/v1/catalog
curl -X POST -H "X-API-Key: client1_key_123" -H "Content-Type: application/json" -d '{"model_alias":"llama3-8b-instruct"}' http://127.0.0.1:8000/v1/models/ensure
curl -X POST -H "X-API-Key: client1_key_123" -H "Content-Type: application/json" -d '{"model_alias":"llama3-8b-instruct","task_type":"chat"}' http://127.0.0.1:8000/v1/leases
curl -X POST -H "X-API-Key: client1_key_123" -H "Content-Type: application/json" -d '{"lease_id":"<LEASE_ID>","messages":[{"role":"user","content":"Hola"}]}' http://127.0.0.1:8000/v1/chat/completions
curl -H "X-API-Key: client1_key_123" http://127.0.0.1:8000/v1/usage/summary
```

## Ejemplos Invoke-RestMethod
```powershell
$h = @{"X-API-Key"="client1_key_123"}
Invoke-RestMethod -Headers $h -Uri "http://127.0.0.1:8000/v1/catalog"
Invoke-RestMethod -Headers $h -Method Post -ContentType "application/json" -Body '{"model_alias":"llama3-8b-instruct"}' -Uri "http://127.0.0.1:8000/v1/models/ensure"
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
