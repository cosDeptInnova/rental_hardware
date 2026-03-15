import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.gpu_agent.models.db_models import Base, BackendInstance, GpuStateSnapshot
from apps.gpu_agent.services import capacity_handoff_service as svc


def _db(tmp_path):
    db_path = tmp_path / "handoff.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _seed_backend(
    db,
    instance_id: str,
    model_alias: str,
    tenant: str = "interno",
    drainable: bool = True,
    critical: bool = False,
    service_tier: str = "production_replicas",
    port: int = 9001,
):
    db.add(
        BackendInstance(
            instance_id=instance_id,
            tenant_id=tenant,
            model_alias=model_alias,
            task_type="chat",
            engine="llama_cpp",
            gpu_device="CUDA0",
            host="127.0.0.1",
            port=port,
            pid=1000 + len(instance_id),
            status="running",
            extra_json=json.dumps({"command": ["llama-server"]}),
            drainable=drainable,
            critical=critical,
            service_tier=service_tier,
            restore_priority=10,
        )
    )
    db.commit()


def test_snapshot_creation(tmp_path, monkeypatch):
    db = _db(tmp_path)
    _seed_backend(db, "i1", "llama3-8b-instruct")

    monkeypatch.setattr(
        svc,
        "collect_gpu_metrics",
        lambda: {
            "timestamp": "2026-01-01T00:00:00",
            "gpus": [{"index": "0", "uuid": "GPU-0", "name": "X", "memory_total_mib": 24576, "memory_used_mib": 12000}],
            "compute_apps": [{"gpu_uuid": "GPU-0", "gpu_index": "0", "pid": 1002, "process_name": "llama", "used_gpu_memory_mib": 8000}],
        },
    )
    out = svc.create_snapshot(db, lease_id="L1", tenant_id="cliente1", request_id="r1")
    assert out["snapshot_id"]
    assert Path(out["path"]).exists()


def test_candidate_selection_only_drainable_and_non_critical(tmp_path):
    db = _db(tmp_path)
    _seed_backend(db, "i1", "m1", drainable=True, critical=False)
    _seed_backend(db, "i2", "m2", drainable=False, critical=False)
    _seed_backend(db, "i3", "m3", drainable=True, critical=True)

    candidates = svc.select_drain_candidates(db)
    ids = [c["instance_id"] for c in candidates]
    assert "i1" in ids
    assert "i2" not in ids
    assert "i3" not in ids


def test_release_dry_run_returns_controlled_error_when_not_enough(tmp_path, monkeypatch):
    db = _db(tmp_path)
    _seed_backend(db, "i1", "m1", drainable=True)
    monkeypatch.setattr(svc, "create_snapshot", lambda *args, **kwargs: {"snapshot_id": "s1"})
    seq = iter(
        [
            {"timestamp": "t0", "gpus": [{"index": "0", "uuid": "GPU-0", "name": "x", "memory_total_mib": 24000, "memory_used_mib": 22000}], "compute_apps": []},
            {"timestamp": "t1", "gpus": [{"index": "0", "uuid": "GPU-0", "name": "x", "memory_total_mib": 24000, "memory_used_mib": 22000}], "compute_apps": []},
            {"timestamp": "t2", "gpus": [{"index": "0", "uuid": "GPU-0", "name": "x", "memory_total_mib": 24000, "memory_used_mib": 22000}], "compute_apps": []},
        ]
    )
    monkeypatch.setattr(svc, "collect_gpu_metrics", lambda: next(seq))

    out = svc.release_capacity(db, target_free_vram_mib=4000, safety_margin_mib=0, dry_run=True)
    assert out["snapshot_id"] == "s1"
    assert out["dry_run"] is True
    assert out["error_code"] == "insufficient_safe_capacity"
    assert out["ok"] is False


def test_restore_idempotent_does_not_duplicate_same_host_port(tmp_path):
    db = _db(tmp_path)
    _seed_backend(db, "i-existing", "m1", tenant="t1", drainable=True, port=9100)

    payload = {
        "backends_known": [
            {
                "instance_id": "x",
                "status": "running",
                "gpu_device": "CUDA0",
                "model_alias": "m1",
                "tenant_id": "t1",
                "host": "127.0.0.1",
                "port": 9100,
                "restore_priority": 5,
            }
        ]
    }
    snap = GpuStateSnapshot(snapshot_id="s1", gpu_index=0, snapshot_json=json.dumps(payload))
    db.add(snap)
    db.commit()

    out = svc.restore_state(db, snapshot_id="s1", dry_run=True)
    assert out["ok"]
    assert out["skipped"][0]["reason"] == "already_active"
