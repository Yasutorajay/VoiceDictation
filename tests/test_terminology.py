from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import load_config
from app.postprocess.modes import bilingual_spacing
from app.postprocess.terminology import TerminologyCorrector, load_terminology


def test_ai_terms_correct_common_mixed_language_errors() -> None:
    corrector = TerminologyCorrector(
        {
            "Claude Code": ["cloud code", "克劳德 code"],
            "Codex": ["code x", "扣得克斯"],
            "GitHub Copilot": ["github co pilot"],
        }
    )
    text = "我用 cloud code 和 code x，再试试 github co pilot"
    assert corrector.apply(text) == "我用 Claude Code 和 Codex，再试试 GitHub Copilot"


def test_term_matching_is_case_insensitive_and_prefers_longer_aliases() -> None:
    corrector = TerminologyCorrector(
        {"Claude": ["cloud"], "Claude Code": ["cloud code"]}
    )
    assert corrector.apply("CLOUD CODE talks to cloud") == "Claude Code talks to Claude"


def test_short_latin_alias_does_not_replace_inside_words() -> None:
    corrector = TerminologyCorrector({"RAG": ["rag"]})
    assert corrector.apply("drag the RAG pipeline") == "drag the RAG pipeline"


def test_user_terminology_overrides_builtin_alias_owner(tmp_path: Path) -> None:
    builtin = tmp_path / "builtin.yaml"
    builtin.write_text(
        "terms:\n  - canonical: Codex\n    aliases: [code x]\n",
        encoding="utf-8",
    )
    user = tmp_path / "user.yaml"
    user.write_text(
        "terms:\n  - canonical: My Codex\n    aliases: [code x]\n",
        encoding="utf-8",
    )
    terms = load_terminology(builtin, user)
    assert TerminologyCorrector(terms).apply("code x") == "My Codex"


def test_invalid_user_terminology_falls_back_to_builtin(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "terminology.yaml").write_text("terms: [broken", encoding="utf-8")
    user = tmp_path / "config.yaml"
    user.write_text(f"paths:\n  data_dir: '{data_dir.as_posix()}'\n", encoding="utf-8")

    cfg = load_config(user_path=user)
    assert "Claude Code" in cfg["terminology"]["terms"]


def test_builtin_ai_dictionary_contains_core_products() -> None:
    terms = load_terminology(ROOT / "resources" / "ai_terms.yaml")
    for canonical in (
        "Claude Code",
        "Codex",
        "OpenAI",
        "Anthropic",
        "MCP",
        "GPT-5.6",
        "Kimi",
        "豆包",
        "Manus",
        "Perplexity",
        "Sora",
        "Midjourney",
        "Seedance",
    ):
        assert canonical in terms


def test_keyboard_and_ai_spoken_forms_are_normalized() -> None:
    terms = load_terminology(ROOT / "resources" / "ai_terms.yaml")
    corrector = TerminologyCorrector(terms)

    corrected = corrector.apply("双 G F 十打开 chat gpt")
    assert corrected == "双击 F10打开 ChatGPT"
    assert bilingual_spacing(corrected) == "双击 F10 打开 ChatGPT"
    corrected = corrector.apply("用 gpt 五点六和 deep seek")
    assert corrected == "用 GPT-5.6和 DeepSeek"
    assert bilingual_spacing(corrected) == "用 GPT-5.6 和 DeepSeek"


def test_loads_all_installed_user_term_packs(tmp_path: Path) -> None:
    builtin = tmp_path / "builtin.yaml"
    builtin.write_text("terms: []\n", encoding="utf-8")
    installed = tmp_path / "terminology"
    installed.mkdir()
    (installed / "brands.yaml").write_text(
        "terms:\n  - canonical: MyBrand\n    aliases: [my brand]\n",
        encoding="utf-8",
    )

    terms = load_terminology(builtin, installed_dir=installed)

    assert TerminologyCorrector(terms).apply("my brand") == "MyBrand"


def test_common_english_terms_normalize_token_and_spoken_forms() -> None:
    terms = load_terminology(ROOT / "resources" / "ai_terms.yaml")
    corrector = TerminologyCorrector(terms)
    assert corrector.apply("token tokens tokenization tokenizer") == "Token Token Token Token"
    assert corrector.apply("托肯和令牌") == "Token和Token"
