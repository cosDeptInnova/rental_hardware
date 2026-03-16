from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass

import psutil

from app.core.schemas import ServiceType
from app.scheduler.admission import ManagedWorker
from app.supervisor.windows_jobs import WindowsJob


@dataclass
class ManagedProcess:
    worker_id: str
    tenant_id: str | None
    service_type: ServiceType
    gpu_index: int
    reserved_vram_mb: int
    reclaimable: bool
    priority: int
    process: subprocess.Popen
    status: str = "idle"
    job: WindowsJob | None = None

    @property
    def busy(self) -> bool:
        return self.status == "busy"


class ProcessManager:
    def __init__(self) -> None:
        self._workers: dict[str, ManagedProcess] = {}

    def spawn_dummy_worker(
        self,
        service_type: ServiceType,
        gpu_index: int,
        reserved_vram_mb: int,
        reclaimable: bool,
        priority: int,
        tenant_id: str | None = None,
        sleep_seconds: int = 300,
    ) -> ManagedProcess:
        worker_id = str(uuid.uuid4())
        cmd = [
            sys.executable,
            "-m",
            "app.workers.dummy_worker",
            "--worker-id",
            worker_id,
            "--gpu-index",
            str(gpu_index),
            "--sleep-seconds",
            str(sleep_seconds),
        ]

        if os.name == "nt":
            job = WindowsJob(f"gpu-broker-{worker_id}")
            proc = job.spawn(cmd)
        else:
            job = None
            proc = subprocess.Popen(cmd)

        managed = ManagedProcess(
            worker_id=worker_id,
            tenant_id=tenant_id,
            service_type=service_type,
            gpu_index=gpu_index,
            reserved_vram_mb=reserved_vram_mb,
            reclaimable=reclaimable,
            priority=priority,
            process=proc,
            job=job,
        )
        self._workers[worker_id] = managed
        return managed

    def list_workers(self) -> list[ManagedWorker]:
        out: list[ManagedWorker] = []
        for w in self._workers.values():
            if w.process.poll() is not None and w.status != "stopped":
                w.status = "stopped"
            out.append(
                ManagedWorker(
                    worker_id=w.worker_id,
                    tenant_id=w.tenant_id,
                    gpu_index=w.gpu_index,
                    reserved_vram_mb=w.reserved_vram_mb,
                    reclaimable=w.reclaimable,
                    priority=w.priority,
                    busy=w.busy,
                    service_type=w.service_type,
                )
            )
        return out

    def graceful_stop(self, worker_id: str) -> None:
        worker = self._workers[worker_id]
        if worker.process.poll() is not None:
            worker.status = "stopped"
            return

        worker.status = "stopping"
        if os.name == "nt":
            worker.process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            worker.process.terminate()

    def hard_kill(self, worker_id: str) -> None:
        worker = self._workers[worker_id]

        if worker.job is not None:
            worker.job.terminate_all(1)
        else:
            try:
                psutil.Process(worker.process.pid).kill()
            except psutil.Error:
                worker.process.kill()

        worker.status = "stopped"

    def reclaim(self, worker_ids: list[str], graceful_timeout: float = 3.0) -> None:
        for worker_id in worker_ids:
            self.graceful_stop(worker_id)

        deadline = time.time() + graceful_timeout
        while time.time() < deadline:
            alive = []
            for worker_id in worker_ids:
                proc = self._workers[worker_id].process
                if proc.poll() is None:
                    alive.append(worker_id)
            if not alive:
                return
            time.sleep(0.2)

        for worker_id in worker_ids:
            proc = self._workers[worker_id].process
            if proc.poll() is None:
                self.hard_kill(worker_id)
