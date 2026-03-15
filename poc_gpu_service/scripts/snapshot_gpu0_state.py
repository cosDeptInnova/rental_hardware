import argparse
import json

from apps.gpu_agent.core.bootstrap import init_db
from apps.gpu_agent.db.session import SessionLocal
from apps.gpu_agent.services.capacity_handoff_service import create_snapshot


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lease_id", default=None)
    parser.add_argument("--tenant_id", default=None)
    parser.add_argument("--notes", default="manual_snapshot")
    parser.add_argument("--request_id", default="script-snapshot")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        result = create_snapshot(db, lease_id=args.lease_id, tenant_id=args.tenant_id, notes=args.notes, request_id=args.request_id)
        print(json.dumps(result, indent=2))
    finally:
        db.close()
