# VoiceDictation 源码恢复状态

恢复日期：2026-08-06

## 已恢复

- 项目入口、配置、构建脚本、资源、文档和测试已恢复到 `F:\VoiceDictation-RanLiAiJay-final\yuanma`。
- 历史会话记录中的 30 个后期新增文件已全部找回。
- `data\models` 已从幸存交付包恢复，共 34 个文件；逐文件 SHA-256 一致。
- 原有 `dist` 未被删除或覆盖。
- 中文路径及外置中文模型目录下的 SenseVoice `tokens.txt` 加载和解码问题已修复。
- 便携配置优先使用程序根目录 `config.yaml`，模型和日志路径均锚定解析后的 `data_dir`。
- 日志清理仅允许处理 `data_dir\logs` 内的旧 `.log`、`.wav`，并保留 `app.log`。
- 已恢复历史快捷键别名、非法快捷键安全回退和中文语气词安全清理。
- 已恢复并验证 F10 本次结果复制、热键捕获/即时生效、托盘实时热键、开机启动确认和用户词库管理。
- 已扩展热门 AI 品牌和键盘口语术语；多个用户词库会在重启后合并加载。

## 源码边界

原始完整 Python 源码曾在更早时间丢失。当前项目中大部分模块已恢复为可读源码；以下五个核心模块使用从最后交付 EXE 提取的 Python 3.12 字节码作为权威运行实现：

- `app\application.pyc`
- `app\audio\capture.pyc`
- `app\hotkey\fsm.pyc`
- `app\hotkey\listener.pyc`
- `app\ui\overlay.pyc`

它们的不完整反编译文本保存在 `recovery_artifacts\incomplete_decompilation`，仅供取证参考，不参与运行。

## 验证结果

- `python -m compileall -q app tests scripts tools`：通过。
- `python -m pytest -q`：197 项全部通过。
- 项目路径实际模型加载：通过。
- 中文路径实际模型加载和 `zh.wav` 中文识别：通过。
- 静态密钥扫描：未发现硬编码密钥。
- 独立代码审查发现的热键混用、词库扩展名冲突和便携图标问题均已修复并回归通过。
- 安全审查要求交付包不含 `data\logs`、录音、识别文本或本机绝对路径；构建脚本已加入强制清理和断言。

## 维护要求

- 不要删除上述五个 `.pyc` 文件；当前 Python 版本必须保持 3.12。
- 修改后运行 `python -m pytest -q`。
- 构建前确认 `data\models` 完整；构建脚本只允许输出到项目 `dist`。

