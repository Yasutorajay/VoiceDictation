from pathlib import Path

from app.dictionary_manager import DictionaryManager
from app.postprocess.terminology import TerminologyCorrector, load_terminology


def test_user_terms_can_be_added_edited_and_removed(tmp_path: Path) -> None:
    manager = DictionaryManager(tmp_path / "terminology")
    manager.save_user_term("GPT Image 2", ["gpt image 二", "gpt 一米几二"])
    assert manager.list_user_terms()[0]["canonical"] == "GPT Image 2"
    manager.save_user_term("GPT Image 2", ["gpt image 2"], original="GPT Image 2")
    assert manager.list_user_terms()[0]["aliases"] == ["gpt image 2"]
    manager.save_user_term("GPT Image 2", ["一米几二"])
    assert manager.list_user_terms() == [{"canonical": "GPT Image 2", "aliases": ["一米几二"]}]
    manager.remove_user_term("GPT Image 2")
    assert manager.list_user_terms() == []


def test_builtin_terms_fix_spoken_ai_and_mandarin_forms(tmp_path: Path) -> None:
    terms = load_terminology(Path("resources/ai_terms.yaml"))
    corrected = TerminologyCorrector(terms).apply("gpt 一米几二，还有君子这个词")
    assert "GPT Image 2" in corrected
    assert "菌子" in corrected


def test_user_terms_file_is_not_exposed_as_removable_package(tmp_path: Path) -> None:
    manager = DictionaryManager(tmp_path / "terminology")
    manager.save_user_term("菌子", ["君子"])

    assert "user_terms" not in {package.id for package in manager.all_packages()}
    try:
        manager.remove("user_terms")
    except ValueError as exc:
        assert "不能" in str(exc)
    assert manager.list_user_terms()[0]["canonical"] == "菌子"
