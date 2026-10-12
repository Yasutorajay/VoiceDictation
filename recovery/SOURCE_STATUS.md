# Source recovery status

Original Python source for several core modules was lost in an earlier recovery
incident. The project kept Python 3.12 bytecode as the runtime authority for:

| Module | Status in this repo |
|--------|---------------------|
| `app/hotkey/fsm.py` | Recovered / present as `.py` |
| `app/ui/overlay.py` | Rewritten clean source (see also `overlay_rewritten_reference.py`) |
| `app/application.py` | **Missing** — only `recovery/bytecode/application.pyc` + incomplete decompile |
| `app/audio/capture.py` | **Missing** — only bytecode + incomplete decompile |
| `app/hotkey/listener.py` | **Missing** — only bytecode + incomplete decompile |

Incomplete Decompyle++ outputs (Python 3.12, not syntax-complete) are under
`recovery/incomplete_decompilation/` for reference only. Do not treat them as
canonical source.

Help wanted: faithful re-implementation or successful decompilation of the three
missing modules under GPL-3.0.
