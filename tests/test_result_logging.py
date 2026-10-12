from pathlib import Path

import numpy as np

from app.worker.pipeline_worker import PipelineWorker


def test_worker_has_no_transcript_or_audio_persistence_path() -> None:
    source = Path(PipelineWorker.__module__.replace(".", "/") + ".py")
    worker_source = source.read_text(encoding="utf-8")

    assert "last_result.txt" not in worker_source
    assert "last_capture.wav" not in worker_source
    assert "job transcript text=" not in worker_source
