# Offline terminology resource

`ai_terms.yaml` is a small, editable alias dictionary used after local SenseVoice
recognition. It contains no model weights and requires no network access at runtime.

The speech models are downloaded separately by `scripts/download_models.py` and remain
under `%LOCALAPPDATA%\\VoiceDictation\\models`.
