from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.core.schemas import ServiceType


@dataclass
class LlamaGatewayResult:
    ok: bool
    status_code: int
    output: dict[str, Any]
    request_tokens: int
    response_tokens: int
    latency_ms: int
    error: str | None = None


class LlamaGateway:
    def __init__(self, base_url: str | None = None, timeout_seconds: float = 25.0) -> None:
        self.base_url = (base_url or settings.llama_server_url).rstrip("/")
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _estimate_tokens(payload: dict[str, Any]) -> int:
        raw = str(payload)
        return max(len(raw) // 4, 1)

    def _mock_response(self, service_type: ServiceType, model_name: str, payload: dict[str, Any]) -> LlamaGatewayResult:
        request_tokens = self._estimate_tokens(payload)
        response_tokens = max(24, request_tokens // 3)

        if service_type == ServiceType.EMBEDDINGS:
            output = {
                "object": "list",
                "model": model_name,
                "data": [
                    {
                        "object": "embedding",
                        "embedding": [0.01, 0.11, 0.02, 0.09, 0.08],
                        "index": 0,
                    }
                ],
                "usage": {
                    "prompt_tokens": request_tokens,
                    "total_tokens": request_tokens,
                },
            }
        else:
            output = {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Respuesta simulada desde gpu-broker (sin llama.cpp disponible).",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": request_tokens,
                    "completion_tokens": response_tokens,
                    "total_tokens": request_tokens + response_tokens,
                },
            }

        return LlamaGatewayResult(
            ok=True,
            status_code=200,
            output=output,
            request_tokens=request_tokens,
            response_tokens=response_tokens,
            latency_ms=5,
        )

    def invoke(self, service_type: ServiceType, model_name: str, payload: dict[str, Any]) -> LlamaGatewayResult:
        if not self.base_url:
            return self._mock_response(service_type=service_type, model_name=model_name, payload=payload)

        endpoint = "/v1/embeddings" if service_type == ServiceType.EMBEDDINGS else "/v1/chat/completions"
        started = time.perf_counter()
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
                response = client.post(endpoint, json={**payload, "model": model_name})
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            body = response.json()

            usage = body.get("usage", {}) if isinstance(body, dict) else {}
            request_tokens = int(usage.get("prompt_tokens", self._estimate_tokens(payload)))
            response_tokens = int(usage.get("completion_tokens", 0))

            return LlamaGatewayResult(
                ok=response.is_success,
                status_code=response.status_code,
                output=body if isinstance(body, dict) else {"raw": body},
                request_tokens=request_tokens,
                response_tokens=response_tokens,
                latency_ms=elapsed_ms,
                error=None if response.is_success else f"llama_http_{response.status_code}",
            )
        except (httpx.HTTPError, ValueError) as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return LlamaGatewayResult(
                ok=False,
                status_code=503,
                output={"error": "llama_unavailable"},
                request_tokens=self._estimate_tokens(payload),
                response_tokens=0,
                latency_ms=elapsed_ms,
                error=str(exc),
            )
