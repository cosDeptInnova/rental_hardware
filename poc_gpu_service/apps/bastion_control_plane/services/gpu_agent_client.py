import httpx
from shared.config import get_settings


class GpuAgentClient:
    def __init__(self):
        self.settings = get_settings()

    async def call(self, method: str, path: str, payload: dict | None = None):
        headers = {"X-Internal-Token": self.settings.internal_agent_token}
        async with httpx.AsyncClient(timeout=self.settings.gpu_agent_timeout_seconds) as client:
            resp = await client.request(
                method,
                f"{self.settings.gpu_agent_base_url}{path}",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()
