# gpu-broker

Broker multi-tenant para alquilar capacidad GPU como servicio gestionado por API.

## Capacidades implementadas

- Reserva de VRAM por tenant y control de concurrencia por tipo de servicio.
- Endpoints de servicio gestionado para:
  - `POST /v1/inference` (proxy/fallback para `llama.cpp` chat/completions).
  - `POST /v1/embeddings` (proxy/fallback para `llama.cpp` embeddings).
- Endpoint de jobs:
  - `POST /v1/jobs` y `GET /v1/jobs/{job_id}`.
- Registro de analítica por petición:
  - tokens de entrada/salida/total,
  - latencia en milisegundos,
  - estado y código de respuesta,
  - modelo y endpoint invocado.
- Analytics para front:
  - `GET /v1/analytics/summary` (por tenant).
  - `GET /v1/admin/analytics/summary` (global admin).

## Integración con llama.cpp

Definir `LLAMA_SERVER_URL` para enrutar peticiones al `llama.cpp server`.
Si no está configurado, el sistema responde con un fallback simulado útil para pruebas de integración y de paneles analytics.

## Arranque local

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
uvicorn app.main:app --reload
```
