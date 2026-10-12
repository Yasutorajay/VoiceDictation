import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()

from app.application import Application
from app.ui.fallback_textbox import FallbackTextBox
from app.inject import clipboard_inject
from app.worker import pipeline_worker
from app.postprocess.modes import bilingual_spacing
from app.single_instance import another_instance_running


def _install_fallback_bridge() -> FallbackTextBox:
    textbox = FallbackTextBox()
    original_inject = clipboard_inject.inject_text

    def bridged_inject(text, cfg, *args, **kwargs):
        result = original_inject(text, cfg, *args, **kwargs)
        if text:
            textbox.set_text(text, None if result.get("ok", False) else result.get("error", "注入失败"))
        return result

    clipboard_inject.inject_text = bridged_inject
    pipeline_worker.inject_text = bridged_inject
    original_postprocess = pipeline_worker.postprocess_text
    def bridged_postprocess(text, cfg, *args, **kwargs):
        result = original_postprocess(text, cfg, *args, **kwargs)
        return bilingual_spacing(result)
    pipeline_worker.postprocess_text = bridged_postprocess
    textbox.start_hotkey_listener()
    return textbox


if __name__ == "__main__":
    if another_instance_running():
        raise SystemExit(0)
    fallback = _install_fallback_bridge()
    try:
        Application().run()
    finally:
        fallback.stop()
