from __future__ import annotations

import re
from dataclasses import dataclass

MODES = ("日常口语", "真实表达", "正式表达", "简洁")


@dataclass
class PostprocessPreferences:
    mode: str = "真实表达"
    preserve_intent: bool = True
    bilingual_spacing: bool = True


def normalize_terms(text: str, terms: dict[str, list[str]] | None = None) -> str:
    for canonical, aliases in (terms or {}).items():
        for alias in sorted(aliases, key=len, reverse=True):
            text = re.sub(re.escape(alias), canonical, text, flags=re.IGNORECASE)
    return text


def bilingual_spacing(text: str) -> str:
    protected: list[str] = []
    def protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"\x00{len(protected)-1}\x00"
    text = re.sub(r"(?:https?://|www\.)\S+|`[^`]+`|[A-Za-z]:\\[^\s]+|\S+@\S+", protect, text)
    text = re.sub(r"(?<=[\u4e00-\u9fff])(?=[A-Za-z0-9])", " ", text)
    text = re.sub(r"(?<=[A-Za-z0-9])(?=[\u4e00-\u9fff])", " ", text)
    for index, value in enumerate(protected):
        text = text.replace(f"\x00{index}\x00", value)
    return text


def apply_mode(text: str, preferences: PostprocessPreferences) -> str:
    if preferences.mode == "简洁":
        text = re.sub(r"(嗯|呃|那个|就是|然后)+", "", text)
        text = re.sub(r"([。！？])\1+", r"\1", text)
    elif preferences.mode == "正式表达" and not preferences.preserve_intent:
        text = text.replace("我觉得", "经评估").replace("不太行", "仍需进一步完善")
    elif preferences.mode == "日常口语":
        text = text.replace("现就", "现在").replace("需进一步", "还需要")
    if preferences.bilingual_spacing:
        text = bilingual_spacing(text)
    return text.strip()
