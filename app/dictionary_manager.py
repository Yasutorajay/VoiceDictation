from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


MAX_DICTIONARY_BYTES = 5 * 1024 * 1024
RESERVED_PACKAGE_IDS = frozenset({"user_terms"})


@dataclass(frozen=True)
class DictionaryPackage:
    id: str
    name: str
    url: str
    license: str
    redistribution: str
    removable: bool = True


class DictionaryManager:
    """管理可审计词库；下载包必须是 JSON/YAML 词条和可核验元数据。"""

    def __init__(self, root: Path, catalog: list[DictionaryPackage] | None = None, source_dirs: list[Path] | None = None) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.catalog = {item.id: item for item in (catalog or [])}
        self.source_dirs = [path for path in (source_dirs or []) if path.exists()]

    def all_packages(self) -> list[DictionaryPackage]:
        """返回内置、资源、用户和已导入词库的统一索引。"""
        packages = dict(self.catalog)
        for directory in [self.root, *self.source_dirs]:
            for path in (*directory.rglob("*.yaml"), *directory.rglob("*.yml"), *directory.rglob("*.json")):
                package_id = path.stem
                if package_id in RESERVED_PACKAGE_IDS:
                    continue
                if package_id in packages:
                    continue
                packages[package_id] = DictionaryPackage(
                    package_id,
                    self._display_name(package_id),
                    f"file://{path}",
                    self._license_for(path),
                    "local_existing",
                    removable=directory == self.root,
                )
        return sorted(packages.values(), key=lambda item: (item.removable, item.name))

    @staticmethod
    def _display_name(package_id: str) -> str:
        names = {
            "ai_terms": "专业 AI 术语词库",
            "personal_terms": "个人品牌词库",
            "terminology": "用户自定义词库",
            "wordnet_3_0": "WordNet 3.0 英文词库",
            "rime_ice_english": "rime-ice 英文词库",
            "jargons_dev_terms": "jargons.dev 技术术语",
            "deepseek_v4_tokens": "DeepSeek V4 Token 词表",
            "external_sources": "外部词库来源目录",
        }
        return names.get(package_id, package_id.replace("_", " "))

    def _license_for(self, path: Path) -> str:
        sidecar = path.with_suffix(".license.txt")
        return sidecar.read_text(encoding="utf-8").splitlines()[0][:80] if sidecar.exists() else "项目现有词库；来源待确认"

    def installed(self) -> list[Path]:
        return sorted(
            path
            for suffix in ("*.yaml", "*.yml", "*.json")
            for path in self.root.glob(suffix)
        )

    @property
    def user_terms_path(self) -> Path:
        return self.root / "user_terms.yaml"

    def list_user_terms(self) -> list[dict[str, Any]]:
        if not self.user_terms_path.is_file():
            return []
        data = yaml.safe_load(self.user_terms_path.read_text(encoding="utf-8")) or {}
        terms = data.get("terms", []) if isinstance(data, dict) else []
        return [term for term in terms if isinstance(term, dict)]

    def save_user_term(self, canonical: str, aliases: list[str], original: str | None = None) -> None:
        canonical = canonical.strip()
        normalized_aliases = list(dict.fromkeys(alias.strip() for alias in aliases if alias.strip()))
        if not canonical or not normalized_aliases:
            raise ValueError("规范词和至少一个别名不能为空")
        terms = self.list_user_terms()
        if original:
            terms = [term for term in terms if str(term.get("canonical", "")) != original]
        terms = [term for term in terms if str(term.get("canonical", "")) != canonical]
        terms.append({"canonical": canonical, "aliases": normalized_aliases})
        payload = yaml.safe_dump({"version": 1, "terms": terms}, allow_unicode=True, sort_keys=False)
        self.user_terms_path.write_text(payload, encoding="utf-8")

    def remove_user_term(self, canonical: str) -> None:
        terms = [term for term in self.list_user_terms() if term.get("canonical") != canonical]
        self.user_terms_path.write_text(
            yaml.safe_dump({"version": 1, "terms": terms}, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def remove(self, package_id: str) -> None:
        if package_id in RESERVED_PACKAGE_IDS:
            raise ValueError("用户自定义词条不能作为词库包删除")
        package = next(
            (item for item in self.all_packages() if item.id == package_id),
            None,
        )
        if package is None:
            raise ValueError("词库不存在")
        if not package.removable:
            raise ValueError("内置词库不可删除")
        for suffix in (".yaml", ".yml", ".json", ".license.txt", ".sha256"):
            path = self.root / f"{package_id}{suffix}"
            if path.exists():
                path.unlink()

    def import_file(self, source: Path, package_id: str, license_text: str) -> Path:
        if source.suffix.lower() not in {".yaml", ".yml", ".json"}:
            raise ValueError("只支持 YAML 或 JSON 词库")
        self._validate_package_id(package_id)
        payload = source.read_bytes()
        self._validate_payload(payload, source.suffix.lower())
        self._remove_package_files(package_id)
        target = self.root / f"{package_id}{source.suffix.lower()}"
        target.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        (self.root / f"{package_id}.sha256").write_text(digest, encoding="ascii")
        (self.root / f"{package_id}.license.txt").write_text(license_text, encoding="utf-8")
        return target

    def download(self, package: DictionaryPackage, checksum: str | None = None) -> Path:
        if not package.url.startswith("https://"):
            raise ValueError("仅允许 HTTPS 词库地址")
        target = self.root / f"{package.id}.json"
        urllib.request.urlretrieve(package.url, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if checksum and digest.lower() != checksum.lower():
            target.unlink(missing_ok=True)
            raise ValueError("词库 SHA256 校验失败")
        (self.root / f"{package.id}.sha256").write_text(digest, encoding="ascii")
        (self.root / f"{package.id}.license.txt").write_text(f"来源：{package.url}\n许可证：{package.license}\n", encoding="utf-8")
        return target

    def download_url(
        self,
        url: str,
        package_id: str,
        license_text: str = "用户提供的 HTTPS 词库；请自行确认来源和许可。",
    ) -> Path:
        if not url.startswith("https://"):
            raise ValueError("仅允许 HTTPS 词库地址")
        self._validate_package_id(package_id)
        suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
        if suffix not in {".yaml", ".yml", ".json"}:
            raise ValueError("下载地址必须指向 YAML 或 JSON 词库")
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "VoiceDictation/1.0"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read(MAX_DICTIONARY_BYTES + 1)
        if len(payload) > MAX_DICTIONARY_BYTES:
            raise ValueError("词库超过 5 MB 限制")
        self._validate_payload(payload, suffix)
        self._remove_package_files(package_id)
        target = self.root / f"{package_id}{suffix}"
        target.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        (self.root / f"{package_id}.sha256").write_text(digest, encoding="ascii")
        (self.root / f"{package_id}.license.txt").write_text(
            f"来源：{url}\n{license_text}\n",
            encoding="utf-8",
        )
        return target

    @staticmethod
    def _validate_package_id(package_id: str) -> None:
        if package_id in RESERVED_PACKAGE_IDS:
            raise ValueError("该词库名称由系统保留")
        if not package_id or any(
            not (character.isalnum() or character in "-_")
            for character in package_id
        ):
            raise ValueError("词库名称只能包含字母、数字、横线和下划线")

    def _remove_package_files(self, package_id: str) -> None:
        for suffix in (".yaml", ".yml", ".json", ".license.txt", ".sha256"):
            (self.root / f"{package_id}{suffix}").unlink(missing_ok=True)

    @staticmethod
    def _validate_payload(payload: bytes, suffix: str) -> None:
        if len(payload) > MAX_DICTIONARY_BYTES:
            raise ValueError("词库超过 5 MB 限制")
        text = payload.decode("utf-8-sig")
        data = json.loads(text) if suffix == ".json" else yaml.safe_load(text)
        if not isinstance(data, dict) or not isinstance(data.get("terms"), list):
            raise ValueError("词库必须包含 terms 列表")
