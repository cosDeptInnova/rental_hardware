import csv
import subprocess
from datetime import datetime


def _run_nvidia_smi(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return result.stdout


def parse_csv(raw: str) -> list[list[str]]:
    reader = csv.reader([line for line in raw.strip().splitlines() if line.strip()])
    rows = []
    for row in reader:
        rows.append([c.strip() for c in row])
    return rows


def collect_gpu_metrics() -> dict:
    query = "index,uuid,name,memory.total,utilization.gpu,utilization.memory,memory.used,power.draw,temperature.gpu"
    raw = _run_nvidia_smi(["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"])
    gpus = []
    for r in parse_csv(raw):
        gpus.append(
            {
                "index": r[0],
                "uuid": r[1],
                "name": r[2],
                "memory_total_mib": float(r[3]),
                "utilization_gpu": float(r[4]),
                "utilization_memory": float(r[5]),
                "memory_used_mib": float(r[6]),
                "power_draw_w": float(r[7]),
                "temperature_gpu_c": float(r[8]),
            }
        )
    raw_apps = _run_nvidia_smi(
        [
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory",
            "--format=csv,noheader,nounits",
        ]
    )
    uuid_to_index = {g["uuid"]: g["index"] for g in gpus}
    apps = []
    for r in parse_csv(raw_apps):
        apps.append(
            {
                "gpu_uuid": r[0],
                "gpu_index": uuid_to_index.get(r[0], "unknown"),
                "pid": int(r[1]),
                "process_name": r[2],
                "used_gpu_memory_mib": float(r[3]),
            }
        )
    return {"timestamp": datetime.utcnow().isoformat(), "gpus": gpus, "compute_apps": apps}
