import argparse
import json

from apps.gpu_agent.core.bootstrap import init_db
from apps.gpu_agent.db.session import SessionLocal
from apps.gpu_agent.services.capacity_handoff_service import release_capacity


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lease_id", default=None)
    parser.add_argument("--tenant_id", default=None)
    parser.add_argument("--target_free_vram_mib", type=int, default=None)
    parser.add_argument("--safety_margin_mib", type=int, default=None)
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--request_id", default="script-release")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        result = release_capacity(
            db,
            target_free_vram_mib=args.target_free_vram_mib,
            safety_margin_mib=args.safety_margin_mib,
            dry_run=args.dry_run,
            lease_id=args.lease_id,
            tenant_id=args.tenant_id,
            request_id=args.request_id,
        )
        print(json.dumps(result, indent=2))
    finally:
        db.close()
