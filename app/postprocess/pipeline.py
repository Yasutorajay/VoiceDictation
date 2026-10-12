from __future__ import annotations

import logging
import re
from typing import Any, Callable

from app.postprocess.fillers import remove_fillers
from app.postprocess.modes import PostprocessPreferences, apply_mode, bilingual_spacing
from app.postprocess.punctuation import polish_punctuation
from app.postprocess.terminology import TerminologyCorrector


logger = logging.getLogger(__name__)


def postprocess_text(
    text: str | None,
    cfg: dict[str, Any] | None,
    *,
    model_punctuate: Callable[[str], str] | None,
) -> str:
    if not text:
        return ""
    config = cfg or {}
    postprocess = config.get("postprocess", {})
    result = str(text).strip()
    if result.startswith("<|"):
        result = re.sub(r"<\|[^|]*\|>", "", result).strip()
    if postprocess.get("remove_fillers", True):
        before = result
        result = remove_fillers(result, enabled=True)
        if before != result:
            logger.debug("fillers changed chars=%d->%d", len(before), len(result))
    terminology = config.get("terminology", {})
    terms = terminology.get("terms", {})
    if terminology.get("enabled", True) and isinstance(terms, dict) and terms:
        result = TerminologyCorrector(terms).apply(result)
    punctuation = config.get("punctuation", {})
    if punctuation.get("enabled", True) and model_punctuate is not None and result:
        punctuated = model_punctuate(result)
        if isinstance(punctuated, str) and punctuated.strip():
            result = punctuated.strip()
    result = polish_punctuation(
        result,
        enabled=bool(postprocess.get("polish_punctuation", True)),
    )
    result = apply_mode(
        result,
        PostprocessPreferences(
            mode=str(postprocess.get("mode", "真实表达")),
            preserve_intent=bool(postprocess.get("preserve_intent", True)),
            bilingual_spacing=False,
        ),
    )
    if postprocess.get("bilingual_spacing", True):
        result = bilingual_spacing(result)
    return result
