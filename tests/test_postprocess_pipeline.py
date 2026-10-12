import logging

from app.postprocess.pipeline import postprocess_text
from app.postprocess.punctuation import polish_punctuation


def test_postprocess_always_returns_text_after_terminology() -> None:
    cfg = {
        "postprocess": {"remove_fillers": True, "polish_punctuation": True},
        "punctuation": {"enabled": False},
        "terminology": {"enabled": True, "terms": {"ChatGPT": ["chat gpt"]}},
    }

    result = postprocess_text("嗯，使用 chat gpt", cfg, model_punctuate=None)

    assert result == "使用 ChatGPT"


def test_postprocess_uses_nonempty_model_punctuation() -> None:
    cfg = {
        "postprocess": {"remove_fillers": False, "polish_punctuation": True},
        "punctuation": {"enabled": True},
        "terminology": {"enabled": False},
    }

    assert postprocess_text("你好", cfg, model_punctuate=lambda _text: "你好。") == "你好。"


def test_postprocess_ignores_empty_model_result() -> None:
    cfg = {
        "postprocess": {"remove_fillers": False, "polish_punctuation": True},
        "punctuation": {"enabled": True},
        "terminology": {"enabled": False},
    }

    assert postprocess_text("你好", cfg, model_punctuate=lambda _text: "") == "你好"


def test_punctuation_handles_empty_and_question_text() -> None:
    assert polish_punctuation(None, enabled=True) == ""
    assert polish_punctuation("现在可以了吗。", enabled=True) == "现在可以了吗？"
    assert polish_punctuation("how are you.", enabled=True) == "How are you?"


def test_punctuation_removes_comma_next_to_sentence_ending() -> None:
    assert polish_punctuation("第一句。，第二句", enabled=True) == "第一句。第二句"
    assert polish_punctuation("第一句，。第二句", enabled=True) == "第一句。第二句"
    assert polish_punctuation("First sentence., Second sentence", enabled=True) == "First sentence. Second sentence"
    assert polish_punctuation("First sentence,. Second sentence", enabled=True) == "First sentence. Second sentence"


def test_punctuation_collapses_mixed_sentence_endings() -> None:
    assert polish_punctuation("这套软件能不能申请软件著作权。？", enabled=True) == "这套软件能不能申请软件著作权？"
    assert polish_punctuation("good morning.。", enabled=True) == "Good morning."
    assert polish_punctuation("你好 good morning.。", enabled=True) == "你好 good morning。"
    assert polish_punctuation("oh thanks..", enabled=True) == "Oh thanks."


def test_punctuation_preserves_decimal_and_url_punctuation() -> None:
    text = "版本 2.0，地址 https://example.com/a,b"

    assert polish_punctuation(text, enabled=True) == text


def test_punctuation_preserves_code_and_url_with_adjacent_symbols() -> None:
    text = '检查 `a.,b` 和 https://example.com/a.,b 之后。，继续'
    assert polish_punctuation(text, enabled=True) == '检查 `a.,b` 和 https://example.com/a.,b 之后。继续'


def test_punctuation_normalizes_sentence_endings_after_protected_text() -> None:
    assert polish_punctuation("Visit https://example.com.。", enabled=True) == "Visit https://example.com."
    assert polish_punctuation("联系 foo@example.com。？", enabled=True) == "联系 foo@example.com？"
    assert polish_punctuation(r"打开 C:\temp\a.txt.。", enabled=True) == r"打开 C:\temp\a.txt。"
    assert polish_punctuation("联系foo@example.com。？然后继续", enabled=True) == "联系foo@example.com？然后继续"
    assert polish_punctuation(r"打开C:\temp\a.txt.。？然后继续", enabled=True) == r"打开C:\temp\a.txt？然后继续"


def test_punctuation_preserves_posix_paths() -> None:
    text = "Open /tmp/a..b and /var/log/app.log."

    assert polish_punctuation(text, enabled=True) == text
    assert polish_punctuation("打开/tmp/a..b", enabled=True) == "打开/tmp/a..b"


def test_punctuation_preserves_windows_path_variants() -> None:
    assert polish_punctuation(r"打开\\server\share\a..b", enabled=True) == r"打开\\server\share\a..b"
    assert polish_punctuation(r"打开C:/temp/a..b", enabled=True) == r"打开C:/temp/a..b"


def test_punctuation_uses_cjk_style_when_cjk_is_protected() -> None:
    assert polish_punctuation("`中文`。？", enabled=True) == "`中文`？"


def test_english_punctuation_converts_fullwidth_comma() -> None:
    assert polish_punctuation('Hello， world。', enabled=True) == 'Hello, world.'


def test_punctuation_preserves_uppercase_urls_and_unquoted_code() -> None:
    for text in ('HTTPS://example.com/a.,b', 'Print(1.,2)', 'Regex /,?/'):
        assert polish_punctuation(text, enabled=True) == text


def test_pipeline_applies_bilingual_spacing_when_enabled() -> None:
    cfg = {
        "postprocess": {
            "remove_fillers": False,
            "polish_punctuation": False,
            "mode": "真实表达",
            "bilingual_spacing": True,
        },
        "punctuation": {"enabled": False},
        "terminology": {"enabled": False},
    }

    assert postprocess_text("使用Python开发", cfg, model_punctuate=None) == "使用 Python 开发"


def test_pipeline_respects_disabled_bilingual_spacing() -> None:
    cfg = {
        "postprocess": {
            "remove_fillers": False,
            "polish_punctuation": True,
            "mode": "真实表达",
            "bilingual_spacing": False,
        },
        "punctuation": {"enabled": False},
        "terminology": {"enabled": False},
    }

    assert postprocess_text("使用Python开发", cfg, model_punctuate=None) == "使用Python开发"


def test_pipeline_combines_terminology_and_bilingual_spacing() -> None:
    cfg = {
        "postprocess": {
            "remove_fillers": False,
            "polish_punctuation": False,
            "mode": "真实表达",
            "bilingual_spacing": True,
        },
        "punctuation": {"enabled": False},
        "terminology": {"enabled": True, "terms": {"ChatGPT": ["chat gpt"]}},
    }

    assert postprocess_text("使用chat gpt开发", cfg, model_punctuate=None) == "使用 ChatGPT 开发"


def test_pipeline_applies_selected_expression_mode_without_double_spacing() -> None:
    cfg = {
        "postprocess": {
            "remove_fillers": False,
            "polish_punctuation": False,
            "mode": "日常口语",
            "preserve_intent": True,
            "bilingual_spacing": True,
        },
        "punctuation": {"enabled": False},
        "terminology": {"enabled": False},
    }

    assert postprocess_text("现就使用Python", cfg, model_punctuate=None) == "现在使用 Python"


def test_debug_logging_does_not_expose_transcript_text(caplog) -> None:
    cfg = {
        "postprocess": {"remove_fillers": True, "polish_punctuation": False},
        "punctuation": {"enabled": False},
        "terminology": {"enabled": False},
    }

    with caplog.at_level(logging.DEBUG):
        assert postprocess_text("嗯，秘密项目", cfg, model_punctuate=None) == "秘密项目"

    assert "秘密项目" not in caplog.text
