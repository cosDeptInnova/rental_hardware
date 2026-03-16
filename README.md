# gpu-broker

Broker multi-tenant para alquilar capacidad GPU como servicio gestionado por API.

## Arranque local

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
uvicorn app.main:app --reload
```
