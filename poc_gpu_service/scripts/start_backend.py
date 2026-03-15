import argparse
import json
from apps.gpu_agent.db.session import SessionLocal
from apps.gpu_agent.services.backend_service import start_backend


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model_alias", required=True)
    p.add_argument("--tenant_id", required=True)
    p.add_argument("--task_type", default="chat")
    p.add_argument("--gpu_device", default="CUDA0")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=9001)
    args = p.parse_args()
    db = SessionLocal()
    try:
        i = start_backend(db, args.model_alias, args.tenant_id, args.gpu_device, args.task_type, args.host, args.port)
        print(json.dumps({"instance_id": i.instance_id, "pid": i.pid, "status": i.status}, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
