import asyncio
import os
import shlex
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

try:
    import pynvml
except Exception:  # optional runtime dependency
    pynvml = None


@dataclass
class GPUMetric:
    ts: str
    gpu_util: float
    memory_used_mb: float
    power_watts: float
    energy_joules: float


@dataclass
class RunnerResult:
    worker_state: str
    exit_code: Optional[int]
    execution_error: Optional[str]
    output_bytes: int
    output_tokens: int
    billed_seconds: int
    gpu_seconds: float
    peak_vram_mb: int
    metrics: list[GPUMetric]


class NVMLSampler:
    def __init__(self):
        self.enabled = False
        self.handle = None
        self.start_energy_j = None
        if pynvml is None:
            return
        try:
            pynvml.nvmlInit()
            self.handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self.start_energy_j = self._energy_joules()
            self.enabled = True
        except Exception:
            self.enabled = False

    def _energy_joules(self) -> Optional[float]:
        if not self.enabled:
            return None
        try:
            millij = pynvml.nvmlDeviceGetTotalEnergyConsumption(self.handle)
            return float(millij) / 1000.0
        except Exception:
            return None

    def sample(self) -> GPUMetric:
        now = datetime.utcnow().replace(microsecond=0).isoformat()
        if not self.enabled:
            return GPUMetric(ts=now, gpu_util=0.0, memory_used_mb=0.0, power_watts=0.0, energy_joules=0.0)

        try:
            util = float(pynvml.nvmlDeviceGetUtilizationRates(self.handle).gpu)
            mem = pynvml.nvmlDeviceGetMemoryInfo(self.handle)
            power = float(pynvml.nvmlDeviceGetPowerUsage(self.handle)) / 1000.0
            energy_now = self._energy_joules()
            energy = max(0.0, (energy_now or 0.0) - (self.start_energy_j or 0.0))
            return GPUMetric(
                ts=now,
                gpu_util=util,
                memory_used_mb=float(mem.used) / (1024.0 * 1024.0),
                power_watts=power,
                energy_joules=energy,
            )
        except Exception:
            return GPUMetric(ts=now, gpu_util=0.0, memory_used_mb=0.0, power_watts=0.0, energy_joules=0.0)

    def close(self):
        if self.enabled and pynvml is not None:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass


def build_command(workload_name: str, estimated_seconds: int) -> list[str]:
    env_cmd = os.getenv("RUNNER_WORKLOAD_CMD")
    if env_cmd:
        return shlex.split(env_cmd)

    python_code = (
        "import time, math; "
        f"end=time.time()+{min(estimated_seconds, 3600)}; "
        "x=0.0; "
        "\nwhile time.time()<end:\n"
        "  x += math.sqrt(12345.6789)\n"
        "print('workload', '" + workload_name.replace("'", "") + "', int(x)%1000)"
    )
    return ["python", "-c", python_code]


async def run_workload(
    workload_name: str,
    estimated_seconds: int,
    gpu_share: float,
    max_job_seconds: int,
    max_power_watts: float,
    max_energy_joules_per_job: float,
) -> RunnerResult:
    command = build_command(workload_name, estimated_seconds)
    start = time.monotonic()
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=False,
        preexec_fn=os.setsid,
    )

    sampler = NVMLSampler()
    metrics: list[GPUMetric] = []
    collector_stop = threading.Event()
    threshold_triggered: Optional[str] = None

    def collect_metrics():
        nonlocal threshold_triggered
        while not collector_stop.is_set():
            metric = sampler.sample()
            metrics.append(metric)
            if threshold_triggered is None and proc.poll() is None:
                if metric.power_watts > max_power_watts:
                    threshold_triggered = f"power threshold exceeded: {metric.power_watts:.2f}W > {max_power_watts:.2f}W"
                    os.killpg(proc.pid, signal.SIGTERM)
                elif metric.energy_joules > max_energy_joules_per_job:
                    threshold_triggered = f"energy threshold exceeded: {metric.energy_joules:.2f}J > {max_energy_joules_per_job:.2f}J"
                    os.killpg(proc.pid, signal.SIGTERM)
            time.sleep(1.0)

    collector = threading.Thread(target=collect_metrics, daemon=True)
    collector.start()

    timed_out = False
    output = b""
    execution_error = None

    try:
        stdout, _ = await asyncio.to_thread(proc.communicate, timeout=max_job_seconds)
        output = stdout or b""
    except subprocess.TimeoutExpired:
        timed_out = True
        execution_error = f"timeout: exceeded max_job_seconds={max_job_seconds}"
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            stdout, _ = await asyncio.to_thread(proc.communicate, timeout=5)
            output = stdout or b""
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, _ = await asyncio.to_thread(proc.communicate)
            output = stdout or b""
    except Exception as exc:
        execution_error = str(exc)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            pass

    collector_stop.set()
    collector.join(timeout=2)
    metrics.append(sampler.sample())
    sampler.close()

    duration = max(0, int(time.monotonic() - start))
    billed_seconds = min(duration, max_job_seconds)

    exit_code = proc.returncode
    if timed_out:
        worker_state = "timeout"
    elif threshold_triggered:
        worker_state = "killed_threshold"
        execution_error = threshold_triggered
    elif exit_code == 0:
        worker_state = "succeeded"
    else:
        worker_state = "failed"
        if execution_error is None:
            execution_error = f"worker exited with code {exit_code}"

    peak_vram_mb = int(max((m.memory_used_mb for m in metrics), default=0.0))
    gpu_seconds = billed_seconds * gpu_share
    output_tokens = max(0, len(output) // 4)

    return RunnerResult(
        worker_state=worker_state,
        exit_code=exit_code,
        execution_error=execution_error,
        output_bytes=len(output),
        output_tokens=output_tokens,
        billed_seconds=billed_seconds,
        gpu_seconds=gpu_seconds,
        peak_vram_mb=peak_vram_mb,
        metrics=metrics,
    )
