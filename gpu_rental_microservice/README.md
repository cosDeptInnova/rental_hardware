# GPU Rental Microservice (FastAPI)

Microservicio de ejemplo para exponer cómputo alquilado de forma **robusta, segura y medible**,
pensado para una **PoC profesional** sobre una GPU dedicada.

## Qué resuelve

- Autenticación por **API Key** con hash en base de datos.
- **Scopes** por cliente (`jobs:write`, `jobs:read`, `usage:read`).
- **Cuotas y límites** por acuerdo comercial:
  - requests por minuto
  - jobs concurrentes
  - tiempo máximo por job
  - bytes de entrada máximos
  - consumo mensual en unidades facturables
- **Medición de consumo** para pricing:
  - número de peticiones
  - bytes de entrada/salida
  - duración del job
  - segundos facturables
  - `gpu_seconds`
  - pico de VRAM (`peak_vram_mb`)
- **Idempotencia** para evitar doble cargo.
- **Audit log** y métricas Prometheus.
- Estructura preparada para usar Redis/PostgreSQL en producción.

## Modelo recomendado de control y pricing

Para una PoC de alquiler de GPU, los parámetros más útiles para regular flujo y consumo son:

1. **requests_per_minute**  
   Controla abuso del API y protege la capa HTTP.

2. **max_concurrent_jobs**  
   Es el control más importante si una GPU está dedicada al alquiler. Evita saturar la GPU por paralelismo.

3. **max_job_seconds**  
   Limita trabajos largos que bloquean capacidad.

4. **max_input_bytes**  
   Protege red, memoria y tiempo de deserialización.

5. **monthly_credit_limit**  
   Permite cortar servicio al llegar al consumo pactado.

6. **gpu_seconds** *(métrica de facturación principal)*  
   Aproximación práctica para PoC:
   `gpu_seconds = wall_time_seconds * gpu_share`
   - GPU dedicada completa: `gpu_share = 1.0`
   - media GPU lógica: `gpu_share = 0.5`

7. **peak_vram_mb** *(métrica de protección o premium)*  
   Útil para recargo por modelos pesados o lotes grandes.

## Precio recomendado para PoC

Usa un esquema simple:

- **Cuota fija mensual** por reserva/canal de acceso.
- **Variable por gpu_second** consumido.
- Opcional:
  - recargo por `peak_vram_mb` sobre umbral
  - recargo por prioridad
  - recargo por horas punta

Ejemplo:
- fee base: 250 €/mes
- 0,0025 € por `gpu_second`
- + 0,0003 € por segundo si `peak_vram_mb > 24000`

## Pricing híbrido (gpu_seconds + tokens + energía)

La facturación mensual estimada en la API (`/v1/usage/me`) usa la siguiente fórmula:

```text
coste_gpu    = total_gpu_seconds * price_per_gpu_second
coste_tokens = ((total_input_tokens + total_output_tokens) / 1000) * price_per_1k_tokens
coste_energia = (total_energy_joules / 3_600_000) * price_per_kwh
coste_total  = coste_gpu + coste_tokens + coste_energia
```

Donde:
- `price_per_gpu_second` viene del contrato del cliente.
- `price_per_1k_tokens` se configura por entorno (`PRICE_PER_1K_TOKENS`).
- `price_per_kwh` se configura por entorno (`PRICE_PER_KWH`).

Además, antes de aceptar un job, el servicio valida límites de contrato por cliente:
- `max_tokens_per_job`
- `monthly_token_limit`
- `max_power_watts`
- `max_energy_joules_per_job`

## Seguridad

- API keys **nunca** en claro en base de datos, solo hash SHA-256.
- Cabecera requerida: `X-API-Key`
- Scope por endpoint.
- Request ID por llamada.
- Headers de seguridad.
- Recomendado en producción:
  - TLS en reverse proxy
  - Redis para rate limit distribuido
  - PostgreSQL para persistencia
  - rotación de claves
  - allowlist IP si el cliente es empresarial

## Arranque

```bash
python -m venv .venv
. .venv/bin/activate  # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
python seed_demo.py
uvicorn app.main:app --host 0.0.0.0 --port 8000
python -m app.worker
```

## API key demo

Tras ejecutar `seed_demo.py`, la clave demo es:

```text
demo-client-key-001
```

## Endpoints

- `GET /healthz`
- `GET /metrics`
- `POST /v1/jobs`
- `GET /v1/jobs/{job_id}`
- `GET /v1/usage/me`
- `GET /v1/admin/clients` (scope admin)

## Limitaciones deliberadas de esta PoC

- Backend SQLite local para simplificar.
- Cola distribuida en Redis + worker dedicado (`app/worker.py`).
- El "trabajo GPU" es simulado y medido como si ocupara una fracción de GPU.
- Para producción, sustituir por ejecución real en worker GPU y persistencia externa.


## Variables nuevas

- `REDIS_URL` (default `redis://localhost:6379/0`)
- `DEFAULT_JOB_MAX_RETRIES`
- `ORPHAN_JOB_TIMEOUT_SECONDS`
