# VoiceDictation

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL%203.0-blue.svg)](LICENSE)

**VoiceDictation** is a Windows 10/11 (64-bit) offline voice dictation tool by **RanLiAiJAY** (brand: 燃砺AiJAY).  
Speech recognition, punctuation, and terminology run locally — no audio upload required.

## License

This project’s own code is released under the **GNU General Public License v3.0** — see [`LICENSE`](LICENSE).  
Third-party libraries, dictionaries, and model weights keep their own licenses — see [`THIRD_PARTY_NOTICES.txt`](THIRD_PARTY_NOTICES.txt).

中文许可证说明：[`LICENSE_NOTE_ZH.md`](LICENSE_NOTE_ZH.md).

## Status / source completeness

Most application modules are present as readable Python source in this repository.

Three historically bytecode-only modules still lack complete recovered `.py` source:

- `app/application.py`
- `app/audio/capture.py`
- `app/hotkey/listener.py`

Details, bytecode snapshots, and incomplete decompilation notes: [`recovery/SOURCE_STATUS.md`](recovery/SOURCE_STATUS.md).

`app/ui/overlay.py` ships as a rewritten open source implementation.  
`app/hotkey/fsm.py` is present as `.py`.

For a ready-to-run Windows build, use **GitHub Releases** portable/installer assets when published (large model weights are not kept in git).

## Run from source (Windows, Python 3.12 recommended)

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
# Place ASR / punct / VAD models under data\models (see data\models\README.md)
copy config.default.yaml config.yaml
python main.py
```

Requirements: Windows 10/11 x64, microphone permission, models on disk.

> Note: until the three missing modules are restored as `.py`, running purely from this git tree may require placing the Python 3.12 `.pyc` files from `recovery/bytecode/` into the matching `app/` paths (same CPython 3.12), or using a Release portable build.

## Default hotkeys

- Hold **Right Alt** + press **middle mouse** to record (release Right Alt to stop)
- Double-tap **F10** for the fallback text box

See [`USER_GUIDE_ZH.md`](USER_GUIDE_ZH.md) for the full Chinese user guide.

## Repository layout

- `app/` — application modules
- `scripts/` — build / package helpers
- `tests/` — pytest suite
- `resources/` — dictionaries and assets
- `installer/` — Inno Setup scripts (if present)
- `recovery/` — bytecode + recovery notes for missing modules

## Contributing

Bug reports and GPL-compatible patches welcome — especially help finishing source recovery for the three missing modules.

---

## 中文

VoiceDictation 是 **RanLiAiJAY**（燃砺AiJAY）做的 Windows 本地语音听写工具：识别、标点、术语都在本机完成。

- **许可证**：自有代码 **GPL-3.0**（见 `LICENSE`）；第三方见 `THIRD_PARTY_NOTICES.txt`
- **源码完整度**：大部分模块已开源为 `.py`；`application` / `audio.capture` / `hotkey.listener` 三处仍缺完整源码，见 `recovery/SOURCE_STATUS.md`
- **便携包 / 安装包**：体积大（含模型），放在 GitHub Release，不进 git
- **从源码运行**：Python 3.12 + `pip install -r requirements.txt`，模型放到 `data\models`，再 `python main.py`

官方品牌与支持：RanLiAiJAY / 燃砺AiJAY。
