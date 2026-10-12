from app.postprocess.fillers import remove_fillers


def test_remove_fillers_handles_continuous_chinese() -> None:
    assert remove_fillers("嗯这个方案很好") == "这个方案很好"


def test_remove_fillers_cleans_adjacent_punctuation() -> None:
    assert remove_fillers("嗯，这个方案很好") == "这个方案很好"


def test_contextual_nage_is_not_removed_inside_sentence() -> None:
    assert remove_fillers("我选择那个方案") == "我选择那个方案"


def test_fillers_do_not_corrupt_regular_chinese_words() -> None:
    text = "金额是一百元，账户余额不足，这个名额已经满了，这就是说服力。"

    assert remove_fillers(text) == text
