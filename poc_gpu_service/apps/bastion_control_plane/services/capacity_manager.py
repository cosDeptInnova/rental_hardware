from apps.bastion_control_plane.services.gpu_agent_client import GpuAgentClient
from shared.config import get_settings


class CapacityManager:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = GpuAgentClient()

    async def on_lease_create(self, lease_id: str, tenant_id: str, requested_gpu: str) -> dict:
        if not self.settings.enable_gpu0_handoff or requested_gpu != "CUDA0":
            return {"enabled": False, "message": "handoff disabled or non-GPU0 lease"}

        snapshot = await self.client.call("POST", "/internal/gpu/0/snapshot", {"lease_id": lease_id, "tenant_id": tenant_id, "notes": "lease_create"})
        release = await self.client.call(
            "POST",
            "/internal/gpu/0/release",
            {
                "lease_id": lease_id,
                "tenant_id": tenant_id,
                "target_free_vram_mib": self.settings.client_gpu0_target_free_vram_mib,
                "safety_margin_mib": self.settings.client_gpu0_safety_margin_mib,
                "dry_run": False,
            },
        )
        status = await self.client.call("GET", "/internal/gpu/0/status")
        return {"enabled": True, "snapshot": snapshot, "release": release, "status": status}

    async def on_lease_close(self, lease_id: str) -> dict:
        if not self.settings.enable_gpu0_handoff or not self.settings.client_gpu0_restore_on_disconnect:
            return {"enabled": False, "message": "restore disabled"}
        return await self.client.call("POST", "/internal/gpu/0/restore", {"lease_id": lease_id, "dry_run": False})
