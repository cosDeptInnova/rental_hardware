from pathlib import Path


def build_llama_command(llama_server_path: str, model_path: str, host: str, port: int, gpu_device: str, ctx_size: int, parallel: int) -> list[str]:
    exe = Path(llama_server_path)
    if exe.suffix.lower() != ".exe":
        raise ValueError("llama_server_path must point to llama-server.exe")
    if gpu_device not in {"CUDA0", "CUDA1"}:
        raise ValueError("gpu_device must be CUDA0 or CUDA1")
    if port < 1024 or port > 65535:
        raise ValueError("invalid port")
    main_gpu = "0" if gpu_device == "CUDA0" else "1"
    return [
        str(exe), "--model", str(Path(model_path)), "--host", host, "--port", str(port),
        "--device", gpu_device, "--split-mode", "none", "--main-gpu", main_gpu,
        "--n-gpu-layers", "-1", "--ctx-size", str(ctx_size), "--parallel", str(parallel),
        "--flash-attn", "auto", "--cont-batching",
    ]
