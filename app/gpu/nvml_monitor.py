from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GpuProcessInfo:
    pid: int
    used_gpu_memory: int | None


@dataclass
class GpuSnapshot:
    index: int
    name: str
    uuid: str
    total_mb: int
    used_mb: int
    free_mb: int
    gpu_util: int
    processes: list[GpuProcessInfo]


class NvmlMonitor:
    def __enter__(self) -> "NvmlMonitor":
        try:
            from pynvml import nvmlInit

            nvmlInit()
            self._available = True
        except Exception:
            self._available = False
        return self


    @property
    def available(self) -> bool:
        return getattr(self, "_available", False)

    def __exit__(self, exc_type, exc, tb) -> None:
        if not getattr(self, "_available", False):
            return
        try:
            from pynvml import nvmlShutdown

            nvmlShutdown()
        except Exception:
            return

    def snapshots(self) -> list[GpuSnapshot]:
        if not getattr(self, "_available", False):
            return []

        from pynvml import (  # type: ignore
            NVMLError,
            nvmlDeviceGetComputeRunningProcesses_v3,
            nvmlDeviceGetCount,
            nvmlDeviceGetHandleByIndex,
            nvmlDeviceGetMemoryInfo,
            nvmlDeviceGetName,
            nvmlDeviceGetUUID,
            nvmlDeviceGetUtilizationRates,
        )

        items: list[GpuSnapshot] = []
        count = nvmlDeviceGetCount()

        for i in range(count):
            handle = nvmlDeviceGetHandleByIndex(i)
            mem = nvmlDeviceGetMemoryInfo(handle)
            util = nvmlDeviceGetUtilizationRates(handle)

            processes: list[GpuProcessInfo] = []
            try:
                running = nvmlDeviceGetComputeRunningProcesses_v3(handle)
                for proc in running:
                    processes.append(
                        GpuProcessInfo(
                            pid=proc.pid,
                            used_gpu_memory=getattr(proc, "usedGpuMemory", None),
                        )
                    )
            except NVMLError:
                pass

            name = nvmlDeviceGetName(handle)
            uuid = nvmlDeviceGetUUID(handle)

            items.append(
                GpuSnapshot(
                    index=i,
                    name=name.decode() if isinstance(name, bytes) else str(name),
                    uuid=uuid.decode() if isinstance(uuid, bytes) else str(uuid),
                    total_mb=mem.total // (1024 * 1024),
                    used_mb=mem.used // (1024 * 1024),
                    free_mb=mem.free // (1024 * 1024),
                    gpu_util=util.gpu,
                    processes=processes,
                )
            )

        return items
