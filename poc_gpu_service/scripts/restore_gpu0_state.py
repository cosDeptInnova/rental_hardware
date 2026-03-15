import argparse
import json

from apps.gpu_agent.core.bootstrap import init_db
from apps.gpu_agent.db.session import SessionLocal
from apps.gpu_agent.services.capacity_handoff_service import restore_state


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot_id", default=None)
    parser.add_argument("--lease_id", default=None)
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--request_id", default="script-restore")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        result = restore_state(db, snapshot_id=args.snapshot_id, lease_id=args.lease_id, dry_run=args.dry_run, request_id=args.request_id)
        print(json.dumps(result, indent=2))
    finally:
        db.close()
