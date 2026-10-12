from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


WORDNET_SOURCE = "https://wordnet.princeton.edu/"
THUOCL_SOURCE = "https://github.com/thunlp/THUOCL"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_package(target: Path, metadata: dict[str, object], entries: list[dict[str, object]]) -> None:
    payload = {"version": 1, "metadata": metadata, "entries": entries}
    target.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    target.with_suffix(".sha256").write_text(sha256(target), encoding="ascii")


def import_wordnet(source: Path, output: Path) -> None:
    entries: list[dict[str, object]] = []
    for name, part_of_speech in (("index.noun", "noun"), ("index.verb", "verb"), ("index.adj", "adjective"), ("index.adv", "adverb")):
        for line in (source / name).read_text(encoding="utf-8").splitlines():
            if not line or line.startswith(" "):
                continue
            lemma = line.split(" ", 1)[0].replace("_", " ")
            entries.append({"term": lemma, "category": part_of_speech})
    write_package(
        output / "wordnet_3_0.json",
        {
            "name": "Princeton WordNet 3.0",
            "source": WORDNET_SOURCE,
            "license": "WordNet License",
            "modified": "Converted index files to VoiceDictation JSON; underscores changed to spaces.",
        },
        entries,
    )


def import_thuocl(source: Path, output: Path) -> None:
    for path in sorted(source.glob("THUOCL_*.txt")):
        category = path.stem.removeprefix("THUOCL_")
        entries: list[dict[str, object]] = []
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            fields = line.rsplit("\t", 1)
            if not fields or not fields[0].strip():
                continue
            frequency = int(fields[1]) if len(fields) == 2 and fields[1].isdigit() else None
            entries.append({"term": fields[0].strip(), "frequency": frequency})
        write_package(
            output / f"thuocl_{category.lower()}.json",
            {
                "name": f"THUOCL {category}",
                "source": THUOCL_SOURCE,
                "license": "MIT",
                "modified": "Converted official tab-separated lexicon to VoiceDictation JSON.",
            },
            entries,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wordnet", type=Path, required=True)
    parser.add_argument("--thuocl", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    import_wordnet(args.wordnet, args.output)
    import_thuocl(args.thuocl, args.output)


if __name__ == "__main__":
    main()
