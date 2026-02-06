import copy
import json
import os

from aqt import gui_hooks, mw
from aqt.qt import QAction, QMessageBox
from aqt.utils import tooltip

# Default configuration schema for the add-on.
from .config import DEFAULT_CONFIG
# Main conversion pipeline (Yomitan -> target note type).
from .conversion import convert_notes
# Hepburn conversion availability check (bundled pykakasi).
from .hepburn import is_available
# Logging helpers for consistent diagnostics.
from .logging_utils import configure_logging, get_logger
# Settings dialog UI.
from .ui import ConfigDialog

# Prevent overlapping conversions.
_RUNNING = False
# Cache merged config for fast access.
_CONFIG_CACHE = None
# Module logger instance.
_LOGGER = get_logger()
# Track whether the Onigiri sidebar hook is already registered.
_SIDEBAR_HOOKED = False


def _migrate_config(cfg: dict) -> bool:
    # Apply one-way migrations for legacy config keys/structures.
    changed = False

    # Migrate legacy "source_note_type_ids" into singular field.
    if cfg.get("source_note_type_id") is None:
        legacy = cfg.get("source_note_type_ids") or []
        if legacy:
            cfg["source_note_type_id"] = legacy[0]
            changed = True

    # Migrate older POS mappings into the newer "categories" schema.
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

    # Drop deprecated key after migration.
    if "pos_mappings" in cfg:
        cfg.pop("pos_mappings", None)
        changed = True

    # Ensure newly introduced keys exist.
    for key in ("source_fields", "virtual_fields"):
        if key not in cfg:
            cfg[key] = copy.deepcopy(DEFAULT_CONFIG.get(key))
            changed = True

    return changed


def _read_local_config() -> dict:
    # Read the local JSON config, falling back to defaults if missing or invalid.
    path = os.path.join(os.path.dirname(__file__), "config.json")
    if not os.path.exists(path):
        return copy.deepcopy(DEFAULT_CONFIG)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        _LOGGER.exception("Failed to read config.json")
        return copy.deepcopy(DEFAULT_CONFIG)


def _merge_defaults(default: dict, custom: dict) -> dict:
    # Merge a custom config into defaults with special handling for tag_transform.
    if not isinstance(custom, dict):
        return copy.deepcopy(default)
    merged = copy.deepcopy(default)
    for key, value in custom.items():
        # tag_transform must be merged field-by-field to preserve defaults.
        if key == "tag_transform":
            tcfg = value if isinstance(value, dict) else {}
            merged_t = {}
            if "prefix" in tcfg:
                merged_t["prefix"] = tcfg.get("prefix", "")
            else:
                merged_t["prefix"] = default.get("tag_transform", {}).get("prefix", "")
            if "mapping" in tcfg:
                merged_t["mapping"] = tcfg.get("mapping") or {}
            else:
                merged_t["mapping"] = default.get("tag_transform", {}).get("mapping", {})
            if "drop" in tcfg:
                merged_t["drop"] = tcfg.get("drop") or []
            else:
                merged_t["drop"] = default.get("tag_transform", {}).get("drop", [])
            merged["tag_transform"] = merged_t
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_defaults(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_config():
    # Load config, migrate legacy formats, merge with defaults, and configure logging.
    global _CONFIG_CACHE
    cfg = _read_local_config()
    tags_cfg = cfg.get("tags") or {}
    # Backwards-compat fix for a legacy tag prefix.
    if tags_cfg.get("link_tag_prefix") == "_intern::yomitan::VOCAB_AUS_DEM_ES_STAMMT":
        tags_cfg["link_tag_prefix"] = "_intern::yomitan"
        cfg["tags"] = tags_cfg
        _write_local_config(cfg)
    # Apply migrations and persist if anything changed.
    if _migrate_config(cfg):
        _write_local_config(cfg)
    # Merge config with defaults and cache for reuse.
    merged = _merge_defaults(DEFAULT_CONFIG, cfg)
    _CONFIG_CACHE = merged
    configure_logging(_CONFIG_CACHE)
    return merged


def save_config(cfg):
    # Persist config changes and refresh logging.
    global _CONFIG_CACHE
    _write_local_config(cfg)
    _CONFIG_CACHE = cfg
    configure_logging(_CONFIG_CACHE)
    _LOGGER.info("Config saved and reloaded")


def open_config():
    # Open the settings dialog with the current config.
    _LOGGER.info("Opening settings dialog")
    cfg = get_config()
    dlg = ConfigDialog(cfg, save_config, mw)
    dlg.exec()


def run_conversion(manual: bool):
    # Run the conversion pipeline, guarded against re-entrancy.
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
    # Auto-run after sync if enabled.
    cfg = get_config()
    if cfg.get("auto_on_sync"):
        _LOGGER.info("Auto conversion after sync")
        run_conversion(manual=False)


def _menu_enabled() -> bool:
    # Enable/disable menu entries based on the "enabled" setting.
    cfg = get_config()
    return bool(cfg.get("enabled", True))


def init_menu():
    # Register actions in the AJpC menu hook if present, else fall back to menubar.
    api = getattr(mw, "_ajpc_menu_api", None)
    if isinstance(api, dict):
        register = api.get("register")
        if callable(register):
            # Preferred: register into the shared AJpC hook.
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

    # Fallback: create/use a local AJpC menu in the menubar.
    menu = None
    for action in mw.form.menubar.actions():
        if action.text().replace("&", "") == "AJpC":
            menu = action.menu()
            break
    if menu is None:
        menu = mw.form.menubar.addMenu("AJpC")

    # Avoid duplicate entries if the menu already contains these actions.
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


def _init_onigiri_sidebar():
    # Register a sidebar action in Onigiri (if available) so Settings can be opened from the sidebar.
    global _SIDEBAR_HOOKED
    if _SIDEBAR_HOOKED:
        return
    try:
        # Onigiri is optional; skip silently if not installed.
        import Onigiri
    except Exception:
        _LOGGER.debug("Onigiri not available; skipping sidebar registration")
        return

    try:
        # Load the bundled SVG icon (if present) for the sidebar entry.
        icon_svg = ""
        icon_path = os.path.join(os.path.dirname(__file__), "yomitan-icon.svg")
        if os.path.exists(icon_path):
            try:
                with open(icon_path, "r", encoding="utf-8") as f:
                    icon_svg = f.read()
            except Exception:
                _LOGGER.exception("Failed to read yomitan-icon.svg")

        # Provide a sidebar entry that triggers a pycmd we handle below.
        Onigiri.register_sidebar_action(
            entry_id="ajpc-yomitran.settings",
            label="Yomitran Settings",
            command="ajpc_yomitran_open_settings",
            icon_svg=icon_svg,
        )

        def _on_js(handled, cmd, context):
            # Handle the sidebar pycmd and open the settings dialog.
            if cmd == "ajpc_yomitran_open_settings":
                open_config()
                return (True, None)
            return handled

        # Attach to Anki's webview message hook so the pycmd reaches Python.
        gui_hooks.webview_did_receive_js_message.append(_on_js)
        _SIDEBAR_HOOKED = True
        _LOGGER.debug("Registered Onigiri sidebar action")
    except Exception:
        _LOGGER.exception("Failed to register Onigiri sidebar action")



def _write_local_config(cfg: dict):
    # Persist config JSON in the add-on folder.
    try:
        path = os.path.join(os.path.dirname(__file__), "config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        _LOGGER.debug("Wrote config.json to add-on folder")
    except Exception:
        _LOGGER.exception("Failed to write config.json")



# Load config early, then register menu + sidebar hooks.
get_config()
init_menu()
_init_onigiri_sidebar()
gui_hooks.sync_did_finish.append(on_sync)
