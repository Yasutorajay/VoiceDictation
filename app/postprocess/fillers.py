from __future__ import annotations

import re
from typing import Iterable


DEFAULT_FILLERS = (
    "就是说",
    "怎么说呢",
    "然后呢",
    "那个啥",
    "你知道吗",
    "说实话",
    "反正就是",
)
_BOUNDARY = r"(?:(?<=^)|(?<=[\s，,。！？!?、；;]))"
_FILLER_FOLLOW = r"(?=[\s，,。！？!?、；;]|这|那|我|你|他|她|它)"
_ZH_SINGLE_FILLER = re.compile(_BOUNDARY + r"[嗯唔呃额啊]+" + _FILLER_FOLLOW)
_ZH_FILLER_PATTERNS = tuple(
    re.compile(_BOUNDARY + re.escape(value) + _FILLER_FOLLOW)
    for value in DEFAULT_FILLERS
)
_ZH_NAGE = re.compile(
    r"(?:(?<=^)|(?<=[\s，,。！？!?、；;]))那个(?=[\s，,。！？!?、；;]|$)"
)
_EN_FILLER_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bum+\b",
        r"\buh+\b",
        r"\ber+\b",
        r"\bhmm+\b",
        r"\byou know\b",
        r"\bi mean\b",
        r"\bkind of\b",
        r"\bsort of\b",
    )
)
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([，。！？、；：,.!?])")
_LEADING_PUNCT = re.compile(r"^[，,、；;：:]+\s*")
_BETWEEN_CHINESE = re.compile(r"([一-鿿])\s+([一-鿿])")


def remove_fillers(
    text: str,
    fillers: Iterable[str] = DEFAULT_FILLERS,
    *,
    enabled: bool = True,
) -> str:
    if not enabled or not text:
        return text
    values = tuple(value for value in fillers if value)
    patterns = _ZH_FILLER_PATTERNS
    if values != DEFAULT_FILLERS:
        patterns = tuple(
            re.compile(_BOUNDARY + re.escape(value) + _FILLER_FOLLOW)
            for value in values
        )
    cleaned = text
    cleaned = _ZH_SINGLE_FILLER.sub(" ", cleaned)
    for pattern in patterns:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = _ZH_NAGE.sub("", cleaned)
    for pattern in _EN_FILLER_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = _MULTI_SPACE.sub(" ", cleaned)
    cleaned = _SPACE_BEFORE_PUNCT.sub(r"\1", cleaned).strip()
    cleaned = _LEADING_PUNCT.sub("", cleaned)
    cleaned = _BETWEEN_CHINESE.sub(r"\1\2", cleaned)
    return _MULTI_SPACE.sub(" ", cleaned).strip()
