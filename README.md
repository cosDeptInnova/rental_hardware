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
- Cuotas por tenant (día/mes) para requests y tokens:
  - `PUT /v1/admin/quotas/{tenant_id}`.
- Control de sesión en Redis para expulsar/restaurar tenants:
  - `POST /v1/admin/sessions/{tenant_id}/revoke`.
  - `POST /v1/admin/sessions/{tenant_id}/restore`.

## Integración con llama.cpp

Definir `LLAMA_SERVER_URL` para enrutar peticiones al `llama.cpp server`.
Si no está configurado, el sistema responde con un fallback simulado útil para pruebas de integración y de paneles analytics.

## Arquitectura de despliegue (Nginx como único punto de entrada)

Esta configuración deja el sistema listo para el requisito:

- **El frontend/cliente solo ve Nginx** (puerto 80 publicado).
- **El backend FastAPI solo es accesible por Nginx** (sin `ports`, únicamente `expose` y red interna).

Se incluye:

- `Dockerfile` para `api`.
- `docker-compose.yml` con red `backend` marcada como `internal: true`.
- `nginx.conf` como reverse proxy hacia `api:8000`.

Para este broker también queda un path dedicado en Nginx:

- Frontend llama a `/broker-api/*` (mismo host de Nginx).
- Nginx traduce `/broker-api/*` -> `api:8000/v1/*`.

## Arranque local (desarrollo Python)

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows
pip install -e .
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Arranque para despliegue/pruebas con Docker

```bash
docker compose up --build -d
```

Checks rápidos:

```bash
curl -sS http://localhost/health
curl -sS http://localhost/broker-health
```

## Verificación de aislamiento de red

- `api` **no** debe tener puertos publicados al host.
- Toda llamada externa debe entrar por `nginx`.

Comando recomendado:

```bash
docker compose ps
```

Debe mostrar `nginx` con `0.0.0.0:80->80/tcp` y `api` sin puertos publicados.
