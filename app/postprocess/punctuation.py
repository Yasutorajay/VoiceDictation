from __future__ import annotations

import re


_ZH_QUESTION_END = re.compile(r"(吗|呢|么|吧|嘛)([。.!！]?)\s*$")
_EN_QUESTION_START = re.compile(
    r"^\s*(what|who|when|where|why|how|is|are|was|were|do|does|did|can|could|would|will|shall|should|may|might|have|has|had|am|isn't|aren't|don't|doesn't|didn't|can't|couldn't|won't|wouldn't|shouldn't)\b",
    re.IGNORECASE,
)
_DUP_PUNCT = re.compile(r"([。！？!?,，、；;])\1+")
_SPACE_PUNCT = re.compile(r"\s+([，。！？、；：,.!?])")
_TRAILING_COMMA = re.compile(r"[，,]\s*$")
_COMMA_AFTER_SENTENCE_END = re.compile(r"([。！？.!?])[,，]+")
_SENTENCE_END_AFTER_COMMA = re.compile(r"[,，]+([。！？.!?])")
_MIXED_SENTENCE_END = re.compile(r"[。！？.!?]+")
_PROTECTED_TEXT = re.compile(
    r"https?://[^\s，。！？]+|www\.[^\s，。！？]+|`[^`]+`|\\\\[^\s，。！？、；：]+"
    r"|[A-Za-z]:[\\/][^\s，。！？、；：]+"
    r"|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}|\b[A-Za-z_]\w*\([^\n)]*\)"
    r"|/[^/\s]+/(?![A-Za-z0-9._~-])|(?<![A-Za-z0-9_:/])/(?:[^/\s]+/)*[^/\s]+",
    re.IGNORECASE,
)
_TRAILING_PROSE_PUNCTUATION = ".,!?，。！？"


def polish_punctuation(text: str | None, *, enabled: bool) -> str:
    result = str(text or "").strip()
    if not enabled or not result:
        return result
    has_cjk = bool(re.search(r"[一-鿿]", result))
    matches = tuple(_PROTECTED_TEXT.finditer(result))
    protected = tuple(match.group(0).rstrip(_TRAILING_PROSE_PUNCTUATION) for match in matches)
    for index, match in reversed(tuple(enumerate(matches))):
        suffix = match.group(0)[len(protected[index]):]
        result = result[:match.start()] + f"\ufffc{index}\ufffc" + suffix + result[match.end():]
    result = _polish_plain_text(result, has_cjk=has_cjk)
    for index, value in enumerate(protected):
        result = result.replace(f"\ufffc{index}\ufffc", value)
    return result


def _polish_plain_text(result: str, *, has_cjk: bool) -> str:
    result = _SPACE_PUNCT.sub(r"\1", result)
    result = _COMMA_AFTER_SENTENCE_END.sub(r"\1", result)
    result = _SENTENCE_END_AFTER_COMMA.sub(r"\1", result)
    result = _MIXED_SENTENCE_END.sub(_collapse_sentence_end, result)
    result = _DUP_PUNCT.sub(r"\1", result)
    result = re.sub(r"\s{2,}", " ", result).strip()
    if _ZH_QUESTION_END.search(result):
        result = _ZH_QUESTION_END.sub(r"\1？", result)
        result = re.sub(r"[。.!！]+\s*$", "", result)
        if not result.endswith("？"):
            result = result.rstrip("。.!！") + "？"
    if _EN_QUESTION_START.search(result):
        stripped = result.rstrip()
        if stripped[-1] not in ".!?？！":
            result = stripped + "?"
        elif stripped.endswith("."):
            result = stripped[:-1] + "?"
    if not has_cjk:
        result = result.translate(str.maketrans("。，？！；：", ".,?!;:"))
        result = result[0].upper() + result[1:]
    result = _TRAILING_COMMA.sub("", result)
    return _DUP_PUNCT.sub(r"\1", result).strip()


def _collapse_sentence_end(match: re.Match[str]) -> str:
    punctuation = match.group(0)
    if "？" in punctuation:
        return "？"
    if "?" in punctuation:
        return "?"
    if "！" in punctuation:
        return "！"
    if "!" in punctuation:
        return "!"
    if "。" in punctuation:
        return "。"
    return "."
