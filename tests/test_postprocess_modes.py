from app.postprocess.modes import PostprocessPreferences, apply_mode, bilingual_spacing


def test_bilingual_spacing_protects_urls_paths_and_code():
    text = "使用Python访问https://example.com并打开C:\\Temp\\a.txt"
    result = bilingual_spacing(text)
    assert "使用 Python" in result
    assert "https://example.com" in result
    assert "C:\\Temp\\a.txt" in result


def test_modes_are_selectable_and_simplify():
    assert "嗯" not in apply_mode("嗯嗯 这个方案就是很好。", PostprocessPreferences(mode="简洁"))
    assert "经评估" in apply_mode(
        "我觉得这个方案不太行",
        PostprocessPreferences(mode="正式表达", preserve_intent=False),
    )


def test_formal_mode_preserves_claim_strength_when_requested():
    text = "我觉得这个方案不太行"

    assert apply_mode(text, PostprocessPreferences(mode="正式表达", preserve_intent=True)) == text


