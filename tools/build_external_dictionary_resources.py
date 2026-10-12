from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import yaml


def _write_package(target: Path, metadata: dict[str, str], entries: list[str]) -> None:
    payload = {
        "version": 1,
        "metadata": metadata,
        "entries": [{"term": term} for term in sorted(set(entries), key=str.casefold)],
    }
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    target.write_text(text, encoding="utf-8")
    target.with_suffix(".sha256").write_text(
        hashlib.sha256(text.encode("utf-8")).hexdigest(), encoding="ascii"
    )
    target.with_suffix(".license.txt").write_text(
        f"{metadata['license']}\n来源：{metadata['source']}\n版本：{metadata['commit']}\n",
        encoding="utf-8",
    )


def _rime_terms(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    return [
        line.split("\t", 1)[0].strip()
        for line in lines
        if line and not line.startswith(("#", "---", "...")) and "\t" in line
    ]


def _jargons_terms(root: Path) -> list[str]:
    terms = []
    for path in root.rglob("*.mdx"):
        match = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', path.read_text(encoding="utf-8"), re.MULTILINE)
        if match:
            terms.append(match.group(1))
    return terms


def _deepseek_terms(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    model = payload.get("model", {})
    vocabulary = model.get("vocab", {})
    if isinstance(vocabulary, dict):
        return [term for term in vocabulary if term.isascii() and term.strip()]
    return []


def build(source_root: Path, output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    packages = (
        (
            output_root / "rime_ice_english.json",
            {
                "name": "rime-ice 英文词库",
                "source": "https://github.com/jinzaizhichi/rime-ice",
                "commit": "569ff3bc65dd4aec0a26b33c49c8bbdfa8b5fd57",
                "license": "GPL-3.0-only",
                "usage": "资源索引，不作为全量强制替换规则",
            },
            _rime_terms(source_root / "rime" / "en_dicts" / "en.dict.yaml")
            + _rime_terms(source_root / "rime" / "en_dicts" / "en_ext.dict.yaml"),
        ),
        (
            output_root / "jargons_dev_terms.json",
            {
                "name": "jargons.dev 技术术语",
                "source": "https://github.com/jargonsdev/jargons.dev",
                "commit": "903f540552ffbc7d0ed75ae37fe725286dc5ebbc",
                "license": "GPL-2.0-only",
                "usage": "仅提取词条标题作为资源索引",
            },
            _jargons_terms(source_root / "jargonsdev" / "src" / "content" / "dictionary"),
        ),
        (
            output_root / "deepseek_v4_tokens.json",
            {
                "name": "DeepSeek V4 Token 词表",
                "source": "https://github.com/AndersonBY/deepseek-tokenizer",
                "commit": "525044c24386953b542ef5262d0c69d309a5d67f",
                "license": "MIT（仓库 pyproject.toml 声明）",
                "usage": "仅索引可见 ASCII token，不作为强制替换规则",
            },
            _deepseek_terms(source_root / "deepseek" / "src" / "deepseek_tokenizer" / "tokenizer.json"),
        ),
    )
    for target, metadata, entries in packages:
        _write_package(target, metadata, entries)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("output_root", type=Path)
    arguments = parser.parse_args()
    build(arguments.source_root, arguments.output_root)
