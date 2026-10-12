import threading
import time

import numpy as np

from app.asr.engine import AsrEngine


def test_transcribe_serializes_recognizer_access() -> None:
    active = 0
    peak = 0
    guard = threading.Lock()

    class Stream:
        result = type("Result", (), {"text": "result"})()

        def accept_waveform(self, _sample_rate, _audio):
            pass

    class Recognizer:
        def create_stream(self):
            return Stream()

        def decode_stream(self, _stream):
            nonlocal active, peak
            with guard:
                active += 1
                peak = max(peak, active)
            time.sleep(0.02)
            with guard:
                active -= 1

    engine = AsrEngine({"audio": {"sample_rate": 16000}})
    engine._recognizer = Recognizer()
    audio = np.ones(16, dtype=np.float32)
    threads = [threading.Thread(target=engine.transcribe, args=(audio,)) for _ in range(4)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert peak == 1
