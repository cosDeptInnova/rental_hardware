from __future__ import annotations

import argparse
import signal
import time


RUNNING = True


def _handle_signal(signum, frame) -> None:
    del signum, frame
    global RUNNING
    RUNNING = False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--gpu-index", required=True)
    parser.add_argument("--sleep-seconds", type=int, default=300)
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _handle_signal)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    started = time.time()
    while RUNNING and (time.time() - started) < args.sleep_seconds:
        time.sleep(0.5)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
