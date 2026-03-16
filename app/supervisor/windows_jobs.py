from __future__ import annotations

import os
import subprocess

if os.name == "nt":
    import win32api
    import win32con
    import win32job
else:
    win32api = None
    win32con = None
    win32job = None


class WindowsJob:
    def __init__(self, name: str):
        if os.name != "nt":
            raise RuntimeError("WindowsJob is only available on Windows")

        self.name = name
        self.handle = win32job.CreateJobObject(None, name)

        info = win32job.QueryInformationJobObject(
            self.handle,
            win32job.JobObjectExtendedLimitInformation,
        )
        info["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        win32job.SetInformationJobObject(
            self.handle,
            win32job.JobObjectExtendedLimitInformation,
            info,
        )

    def spawn(self, cmd: list[str], cwd: str | None = None, env: dict[str, str] | None = None) -> subprocess.Popen:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        process_handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, False, proc.pid)
        try:
            win32job.AssignProcessToJobObject(self.handle, process_handle)
        finally:
            win32api.CloseHandle(process_handle)
        return proc

    def terminate_all(self, exit_code: int = 1) -> None:
        win32job.TerminateJobObject(self.handle, exit_code)

    def close(self) -> None:
        win32api.CloseHandle(self.handle)
