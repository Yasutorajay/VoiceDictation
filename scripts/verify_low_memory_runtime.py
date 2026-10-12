from __future__ import annotations

import multiprocessing
import os
import time
from pathlib import Path

import psutil

from app.asr.process_engine import ProcessAsrEngine
from app.config import load_config


def megabytes(value: int) -> float:
    return round(value / 1024 / 1024, 1)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_config(root / "config.yaml")
    engine = ProcessAsrEngine(cfg, idle_unload_seconds=1)
    parent = psutil.Process(os.getpid())
    started = time.perf_counter()
    engine.load(load_punctuation=False)
    load_seconds = round(time.perf_counter() - started, 2)
    process = engine._process
    if process is None or process.pid is None:
        raise RuntimeError("Recognition subprocess was not created")
    child = psutil.Process(process.pid)
    print(f"load_seconds={load_seconds}")
    print(f"parent_rss_mb={megabytes(parent.memory_info().rss)}")
    print(f"child_rss_mb={megabytes(child.memory_info().rss)}")
    child_pid = process.pid
    engine.close()
    time.sleep(0.2)
    print(f"child_exited={not psutil.pid_exists(child_pid)}")
    if psutil.pid_exists(child_pid):
        raise RuntimeError("Recognition subprocess did not exit")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
