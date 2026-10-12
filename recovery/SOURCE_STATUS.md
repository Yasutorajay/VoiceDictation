# Source recovery status

| Module | Status |
|--------|--------|
| `app/hotkey/fsm.py` | Present as `.py` (earlier recovery) |
| `app/ui/overlay.py` | Rewritten clean GPL source (HUD API compatible) |
| `app/application.py` | **Restored 2026-10-13** — reconstructed from Python 3.12 bytecode + call sites / tests |
| `app/audio/capture.py` | **Restored 2026-10-13** — reconstructed from bytecode (`sounddevice` capture, levels, trim helpers) |
| `app/hotkey/listener.py` | **Restored 2026-10-13** — reconstructed from bytecode (keyboard observe + WH_MOUSE_LL) |

## Notes

- Canonical first-party license remains **GPL-3.0** (`LICENSE`).
- Bytecode snapshots remain under `recovery/bytecode/` for forensic reference.
- Incomplete Decompyle++ dumps remain under `recovery/incomplete_decompilation/` (not runtime source).
- Restored modules favor faithful API/behavior matching the rest of the tree (`main.py`, FSM, overlay, `PipelineWorker`, tray, settings). Windows-only hooks are unchanged in intent; full end-to-end mic/ASR runtime should be verified on Windows with Release models.

## Verification done on restore

- `py_compile` for the three modules
- Unit/API smoke for `apply_hotkey`, settings wiring, listener suppress rules, capture snapshot/levels (Linux stubs for `tkinter` / `winreg` / `WinDLL`)
