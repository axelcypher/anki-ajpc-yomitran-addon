from __future__ import annotations

import copy
import json
import os
from typing import Any

from ._yomitran_schema import DEFAULT_CONFIG, merge_config


NAMESPACE_KEY = "yomitran"

_STANDALONE_KEYS = {
    "enabled",
    "run_on_sync",
    "run_on_card_added",
    "auto_on_sync",
    "source_note_type_id",
    "source_note_type_ids",
    "source_fields",
    "virtual_fields",
    "categories",
    "hepburn",
    "tags",
    "tag_transform",
}

_TOOLS_ROOT_KEYS = {
    "run_on_sync",
    "run_on_ui",
    "family_gate",
    "card_stages",
    "kanji_gate",
    "mass_linker",
}


class ConfigBackend:
    def __init__(self, addon_dir: str | None = None) -> None:
        if addon_dir is None:
            addon_dir = os.path.dirname(os.path.dirname(__file__))
        self.addon_dir = addon_dir
        self.config_path = os.path.join(self.addon_dir, "config.json")
        self.meta_path = os.path.join(self.addon_dir, "meta.json")

    def _read_root(self) -> dict[str, Any]:
        if not os.path.exists(self.config_path):
            return {}
        try:
            with open(self.config_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write_root(self, data: dict[str, Any]) -> None:
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _read_meta(self) -> dict[str, Any]:
        if not os.path.exists(self.meta_path):
            return {}
        try:
            with open(self.meta_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write_meta(self, data: dict[str, Any]) -> None:
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _migrate_legacy_meta_config(self) -> None:
        meta = self._read_meta()
        meta_cfg = meta.get("config")
        if not isinstance(meta_cfg, dict):
            return

        root_cfg = self._read_root()
        root_is_empty = not isinstance(root_cfg, dict) or not bool(root_cfg)
        if root_is_empty:
            payload, _namespaced = self._extract_payload(meta_cfg)
            migrated = merge_config(DEFAULT_CONFIG, payload)
            self._write_root(migrated)

        meta.pop("config", None)
        self._write_meta(meta)

    def _looks_like_standalone(self, root_cfg: dict[str, Any]) -> bool:
        return any(k in root_cfg for k in _STANDALONE_KEYS)

    def _looks_like_tools_root(self, root_cfg: dict[str, Any]) -> bool:
        return any(k in root_cfg for k in _TOOLS_ROOT_KEYS)

    def _extract_payload(self, root_cfg: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        slot = root_cfg.get(NAMESPACE_KEY)
        if isinstance(slot, dict):
            return copy.deepcopy(slot), True
        if self._looks_like_standalone(root_cfg):
            return copy.deepcopy(root_cfg), False
        if self._looks_like_tools_root(root_cfg):
            return {}, True
        return copy.deepcopy(root_cfg), False

    def load_raw(self) -> tuple[dict[str, Any], bool]:
        self._migrate_legacy_meta_config()
        root_cfg = self._read_root()
        payload, namespaced = self._extract_payload(root_cfg)
        return payload, namespaced

    def load_effective(self) -> tuple[dict[str, Any], bool]:
        raw, namespaced = self.load_raw()
        changed = _migrate_config(raw)
        merged = merge_config(DEFAULT_CONFIG, raw)
        if changed:
            self.save_effective(merged, force_namespaced=namespaced)
        return merged, namespaced

    def save_effective(self, cfg: dict[str, Any], *, force_namespaced: bool | None = None) -> None:
        root_cfg = self._read_root()
        if force_namespaced is None:
            if isinstance(root_cfg.get(NAMESPACE_KEY), dict):
                namespaced = True
            elif self._looks_like_tools_root(root_cfg):
                namespaced = True
            elif self._looks_like_standalone(root_cfg):
                namespaced = False
            else:
                namespaced = False
        else:
            namespaced = bool(force_namespaced)

        out_cfg = copy.deepcopy(cfg) if isinstance(cfg, dict) else copy.deepcopy(DEFAULT_CONFIG)
        if namespaced:
            root = root_cfg if isinstance(root_cfg, dict) else {}
            root[NAMESPACE_KEY] = out_cfg
            self._write_root(root)
            return
        self._write_root(out_cfg)


def _migrate_config(cfg: dict[str, Any]) -> bool:
    changed = False

    if "run_on_sync" not in cfg:
        cfg["run_on_sync"] = bool(cfg.get("auto_on_sync", True))
        changed = True
    if "auto_on_sync" in cfg:
        cfg.pop("auto_on_sync", None)
        changed = True
    if "run_on_card_added" not in cfg:
        cfg["run_on_card_added"] = bool(DEFAULT_CONFIG.get("run_on_card_added", False))
        changed = True

    if cfg.get("source_note_type_id") is None:
        legacy = cfg.get("source_note_type_ids") or []
        if legacy:
            cfg["source_note_type_id"] = legacy[0]
            changed = True

    if not cfg.get("categories"):
        pos = cfg.get("pos_mappings") or {}
        if isinstance(pos, dict) and pos:
            defaults = [
                ("verb", "Verbs", {"source_field": "PartOfSpeech", "values": ["godan", "ichidan", "suru"]}),
                ("adjective", "Adjectives", {"source_field": "PartOfSpeech", "values": ["na", "i", "no"]}),
                ("other", "Other", {"source_field": "PartOfSpeech", "values": []}),
            ]
            categories = []
            for key, name, filt in defaults:
                entry = pos.get(key) or {}
                categories.append(
                    {
                        "id": key,
                        "name": name,
                        "note_type_id": entry.get("note_type_id"),
                        "filter": filt,
                        "field_map": entry.get("field_map") or {},
                    }
                )
            cfg["categories"] = categories
            changed = True

    if "pos_mappings" in cfg:
        cfg.pop("pos_mappings", None)
        changed = True

    for key in ("source_fields", "virtual_fields"):
        if key not in cfg:
            cfg[key] = copy.deepcopy(DEFAULT_CONFIG.get(key))
            changed = True

    # Rename old source field key POS -> PartOfSpeech when present.
    source_fields = cfg.get("source_fields")
    if isinstance(source_fields, list):
        for item in source_fields:
            if not isinstance(item, dict):
                continue
            if str(item.get("name") or "") == "POS":
                item["name"] = "PartOfSpeech"
                if not item.get("label"):
                    item["label"] = "Part of Speech"
                changed = True

    return changed
