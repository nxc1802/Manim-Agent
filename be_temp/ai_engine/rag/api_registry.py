from __future__ import annotations

import re
from pathlib import Path
from typing import Any, TypedDict, cast

import yaml  # type: ignore[import-untyped]


class RegistryEntry(TypedDict, total=False):
    symbol: str
    module_path: str
    category: str
    signature: str
    description: str
    example: str
    deprecated_aliases: list[str]
    common_errors: list[dict[str, str]]


class ManimAPIRegistry:
    """Structured lookup against pre-built ManimCE API registry."""

    def __init__(self, registry_path: Path | None = None):
        if registry_path is None:
            registry_path = Path(__file__).resolve().parent / "data" / "manim_api_registry.yaml"

        self.registry_path = registry_path
        self._data: dict[str, Any] = {"entries": [], "deprecated_aliases": {}}
        self._load()

    def _load(self) -> None:
        if not self.registry_path.exists():
            return
        with open(self.registry_path, encoding="utf-8") as f:
            self._data = yaml.safe_load(f) or {"entries": [], "deprecated_aliases": {}}

    def lookup_symbol(self, symbol: str) -> dict[str, Any] | None:
        """Exact match: 'Text' -> entry for Text mobject."""
        # Check Scene.method format
        for entry in self._data.get("entries", []):
            if entry["symbol"] == symbol:
                return cast(dict[str, Any], entry)
            # Allow matching method name only if unique or prioritized
            if "." in entry["symbol"] and entry["symbol"].split(".")[-1] == symbol:
                return cast(dict[str, Any], entry)
        return None

    def lookup_deprecated(self, symbol: str) -> tuple[str, dict[str, Any]] | None:
        """Check deprecated aliases: 'ShowCreation' -> ('Create', Create entry)."""
        mapping = self._data.get("deprecated_aliases", {})
        if symbol in mapping:
            target = mapping[symbol]
            entry = self.lookup_symbol(target)
            if entry:
                return target, entry
        return None

    def find_similar(self, symbol: str) -> list[dict[str, Any]]:
        """Prefix/substring match for fuzzy cases: 'play_text' -> [Scene.play, Text, Write]."""
        results = []
        symbol_lower = symbol.lower()

        # 1. Exact substrings
        for entry in self._data.get("entries", []):
            entry_sym = entry["symbol"].lower()
            if symbol_lower in entry_sym or entry_sym in symbol_lower:
                results.append(entry)

        # 2. Check common error patterns in entries
        for entry in self._data.get("entries", []):
            if entry in results:
                continue
            for err in entry.get("common_errors", []):
                if re.search(err.get("pattern", ""), symbol, re.I):
                    results.append(entry)
                    break

        return results[:5]

    def resolve_error(self, error_type: str, symbol: str | None) -> list[dict[str, Any]]:
        """Main entry: error -> relevant registry entries (max 5)."""
        if not symbol:
            return []

        # 1. Check deprecated
        dep = self.lookup_deprecated(symbol)
        if dep:
            return [dep[1]]

        # 2. Exact match
        exact = self.lookup_symbol(symbol)
        if exact:
            return [exact]

        # 3. Fuzzy match
        return self.find_similar(symbol)
