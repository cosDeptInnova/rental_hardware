import argparse
import json
from apps.gpu_agent.db.session import SessionLocal
from apps.gpu_agent.services.backend_service import stop_backend


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--instance_id")
    p.add_argument("--pid", type=int)
    args = p.parse_args()
    db = SessionLocal()
    try:
        print(json.dumps(stop_backend(db, args.instance_id, args.pid), indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
