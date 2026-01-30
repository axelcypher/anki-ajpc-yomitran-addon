import copy
import json
import os
import re
import subprocess
import sys

from aqt import gui_hooks, mw
from aqt.qt import QAction, QMessageBox
from aqt.utils import tooltip

from .config import DEFAULT_CONFIG, TAG_MAPPING_DEFAULT, merge_config
from .conversion import convert_notes
from .hepburn import is_available
from .logging_utils import configure_logging, get_logger
from .ui import ConfigDialog

ADDON_NAME = mw.addonManager.addonFromModule(__name__) or __name__
_RUNNING = False
_CONFIG_CACHE = None
_LOGGER = get_logger()
_ROMAJI_SUFFIX_RE = re.compile(r"(Godan|Nidan|Yodan)-[A-Za-z/]+")


def _migrate_config(cfg: dict) -> bool:
    changed = False

    if cfg.get("source_note_type_id") is None:
        legacy = cfg.get("source_note_type_ids") or []
        if legacy:
            cfg["source_note_type_id"] = legacy[0]
            changed = True

    if not cfg.get("categories"):
        pos = cfg.get("pos_mappings") or {}
        if isinstance(pos, dict) and pos:
            defaults = [
                ("verb", "Verbs", {"source_field": "POS", "values": ["godan", "ichidan", "suru"]}),
                ("adjective", "Adjectives", {"source_field": "POS", "values": ["na/i"]}),
                ("other", "Other", {"source_field": "POS", "values": []}),
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

    return changed


def get_config():
    global _CONFIG_CACHE
    cfg = mw.addonManager.getConfig(ADDON_NAME) or {}
    changed = False
    tags_cfg = cfg.get("tags") or {}
    if tags_cfg.get("link_tag_prefix") == "_intern::yomitan::VOCAB_AUS_DEM_ES_STAMMT":
        tags_cfg["link_tag_prefix"] = "_intern::yomitan"
        cfg["tags"] = tags_cfg
        changed = True
    if _migrate_config(cfg):
        changed = True
    if _normalize_tag_mapping(cfg):
        changed = True
    merged = merge_config(DEFAULT_CONFIG, cfg)
    if changed or merged != cfg:
        mw.addonManager.writeConfig(ADDON_NAME, merged)
    _CONFIG_CACHE = merged
    configure_logging(_CONFIG_CACHE)
    return merged


def save_config(cfg):
    global _CONFIG_CACHE
    mw.addonManager.writeConfig(ADDON_NAME, cfg)
    _write_local_config(cfg)
    _CONFIG_CACHE = cfg
    configure_logging(_CONFIG_CACHE)
    _LOGGER.info("Config saved and reloaded")


def open_config():
    _LOGGER.info("Opening settings dialog")
    cfg = get_config()
    dlg = ConfigDialog(cfg, save_config, mw)
    dlg.exec()


def run_conversion(manual: bool):
    global _RUNNING
    if _RUNNING:
        return
    _RUNNING = True
    _LOGGER.info("Conversion started (manual=%s)", manual)
    try:
        convert_notes(get_config(), manual=manual)
        _LOGGER.info("Conversion finished")
    except Exception as exc:
        _LOGGER.exception("Conversion failed")
        tooltip(f"Yomitan import failed: {exc}")
    finally:
        _RUNNING = False


def on_sync(*_):
    cfg = get_config()
    if cfg.get("auto_on_sync"):
        _LOGGER.info("Auto conversion after sync")
        run_conversion(manual=False)


def _menu_enabled() -> bool:
    cfg = get_config()
    return bool(cfg.get("enabled", True))


def init_menu():
    api = getattr(mw, "_ajpc_menu_api", None)
    if isinstance(api, dict):
        register = api.get("register")
        if callable(register):
            register(
                kind="run",
                label="Run Yomitran",
                callback=lambda: run_conversion(manual=True),
                enabled_fn=_menu_enabled,
                order=60,
            )
            register(
                kind="settings",
                label="Yomitran Settings",
                callback=open_config,
                order=30,
            )
            _LOGGER.debug("Registered menu actions via AJpC hook")
            return

    menu = None
    for action in mw.form.menubar.actions():
        if action.text().replace("&", "") == "AJpC":
            menu = action.menu()
            break
    if menu is None:
        menu = mw.form.menubar.addMenu("AJpC")

    existing = {a.text().replace("&", "") for a in menu.actions()}
    if "Run Yomitran" not in existing:
        menu.addSeparator()
        action_run = QAction("Run Yomitran", mw)
        action_run.triggered.connect(lambda: run_conversion(manual=True))
        menu.addAction(action_run)
        _LOGGER.debug("Added menu action: Run Yomitran")

    if "Yomitran Settings" not in existing:
        action_cfg = QAction("Yomitran Settings", mw)
        action_cfg.triggered.connect(open_config)
        menu.addAction(action_cfg)
        _LOGGER.debug("Added menu action: Yomitran Settings")


def _prompt_pykakasi_install():
    if is_available():
        _LOGGER.debug("pykakasi already available")
        return

    box = QMessageBox(mw)
    box.setWindowTitle("pykakasi missing")
    box.setText("pykakasi is required for proper Hepburn conversion.")
    box.setInformativeText("Install now? (Anki may need a restart)")
    install_btn = box.addButton("Install pykakasi", QMessageBox.ButtonRole.AcceptRole)
    decline_btn = box.addButton("Not now", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(install_btn)
    box.exec()

    if box.clickedButton() != install_btn:
        _LOGGER.info("pykakasi install declined")
        return

    mw.progress.start(immediate=True)
    try:
        _LOGGER.info("Installing pykakasi via pip")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pykakasi"])
        tooltip("pykakasi installed. Please restart Anki.")
        _LOGGER.info("pykakasi installed successfully")
    except Exception as exc:
        _LOGGER.exception("pykakasi install failed")
        tooltip(f"pykakasi install failed: {exc}")
    finally:
        mw.progress.finish()


def _write_local_config(cfg: dict):
    try:
        path = os.path.join(os.path.dirname(__file__), "config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        _LOGGER.debug("Wrote config.json to add-on folder")
    except Exception:
        _LOGGER.exception("Failed to write config.json")


def _normalize_tag_mapping(cfg: dict) -> bool:
    tcfg = cfg.get("tag_transform") or {}
    mapping = tcfg.get("mapping")
    if not isinstance(mapping, dict):
        return False
    changed = False
    for key, default_val in TAG_MAPPING_DEFAULT.items():
        cur = mapping.get(key)
        if not isinstance(cur, str):
            continue
        if "?" in cur or _ROMAJI_SUFFIX_RE.search(cur) or any(bad in cur for bad in ("Ã", "ã", "â")):
            mapping[key] = default_val
            changed = True
    if changed:
        tcfg["mapping"] = mapping
        cfg["tag_transform"] = tcfg
        _LOGGER.info("Normalized tag mapping values")
    return changed


get_config()
init_menu()
gui_hooks.sync_did_finish.append(on_sync)
gui_hooks.profile_did_open.append(_prompt_pykakasi_install)
