from shared.config import get_settings


def estimate_cost(input_tokens: int | None, output_tokens: int | None, duration_s: float, response_bytes: int, avg_gpu_watts: float = 120.0) -> dict:
    s = get_settings()
    cost = s.cost_fixed_per_request
    if input_tokens is not None:
        cost += (input_tokens / 1000.0) * s.cost_per_1k_input_tokens
    if output_tokens is not None:
        cost += (output_tokens / 1000.0) * s.cost_per_1k_output_tokens
    cost += duration_s * s.cost_per_second_backend
    cost += (response_bytes / (1024**3)) * s.cost_per_gb_network_egress
    wh = (avg_gpu_watts * duration_s) / 3600.0
    cost += (wh / 1000.0) * s.cost_per_kwh_gpu
    return {"estimated_cost": round(cost, 6), "gpu_energy_est_wh": round(wh, 6), "estimated": input_tokens is None or output_tokens is None}
