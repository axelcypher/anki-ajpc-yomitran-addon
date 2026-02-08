from __future__ import annotations

from datetime import datetime
import html
import json
import os
import time
from typing import Any

from anki import hooks as anki_hooks
from aqt import gui_hooks, mw
from aqt.qt import QTimer
from aqt.utils import tooltip

from . import ModuleSpec
from ._yomitran_backend import ConfigBackend
from ._yomitran_conversion import convert_notes
from ._yomitran_hepburn import is_available
from ._yomitran_logging import configure_logging, get_logger
from ._yomitran_ui import ConfigDialog, ConfigPanel


_BACKEND = ConfigBackend()
_CONFIG_CACHE: dict[str, Any] | None = None
_RUNNING = False
_PENDING_CARD_ADDED_RUN = False
_SESSION_PROCESSED = 0
_WIDGET_CACHE_TTL_SEC = 5.0
_WIDGET_CACHE_KEY = ""
_WIDGET_CACHE_TS = 0.0
_WIDGET_CACHE_UNPROCESSED = 0
_LOGGER = get_logger()
_ADDON_DIR = os.path.dirname(os.path.dirname(__file__))
_RAW_ADD_LOG_PATH = os.path.join(_ADDON_DIR, "ajpc-yomitran-raw-add.jsonl")
_RAW_ADD_LOG_MAX_BYTES = 5 * 1024 * 1024


def get_config(*, reload: bool = False) -> dict[str, Any]:
    global _CONFIG_CACHE
    if not reload and isinstance(_CONFIG_CACHE, dict):
        return _CONFIG_CACHE
    merged, _namespaced = _BACKEND.load_effective()
    _CONFIG_CACHE = merged
    configure_logging(_CONFIG_CACHE, enabled_override=_is_global_debug_enabled())
    return _CONFIG_CACHE


def save_config(cfg: dict[str, Any]) -> None:
    global _CONFIG_CACHE
    next_cfg = dict(cfg or {})
    _BACKEND.save_effective(next_cfg)
    _CONFIG_CACHE = next_cfg
    configure_logging(_CONFIG_CACHE, enabled_override=_is_global_debug_enabled())
    _invalidate_widget_cache()
    _LOGGER.info("Config saved and reloaded")


def run_conversion(manual: bool) -> None:
    global _RUNNING, _SESSION_PROCESSED
    if _RUNNING:
        return
    cfg = get_config(reload=True)
    if not bool(cfg.get("enabled", True)):
        if manual:
            tooltip("Yomitran is disabled in settings.")
        return
    _RUNNING = True
    _LOGGER.info("Conversion started (manual=%s)", manual)
    try:
        result = convert_notes(cfg, manual=manual) or {}
        created = int(result.get("created", 0) or 0)
        if created > 0:
            _SESSION_PROCESSED += created
        _invalidate_widget_cache()
        _LOGGER.info("Conversion finished")
    except Exception as exc:
        _LOGGER.exception("Conversion failed")
        tooltip(f"Yomitran import failed: {exc}")
    finally:
        _RUNNING = False


def _append_raw_add_log(payload: dict[str, Any]) -> None:
    try:
        if os.path.exists(_RAW_ADD_LOG_PATH):
            size = os.path.getsize(_RAW_ADD_LOG_PATH)
            if size >= _RAW_ADD_LOG_MAX_BYTES:
                with open(_RAW_ADD_LOG_PATH, "w", encoding="utf-8") as f:
                    f.write(
                        json.dumps(
                            {
                                "ts": datetime.now().isoformat(timespec="seconds"),
                                "event": "log_truncated",
                                "reason": f"size>={_RAW_ADD_LOG_MAX_BYTES}",
                            },
                            ensure_ascii=False,
                        )
                    )
                    f.write("\n")
        with open(_RAW_ADD_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False))
            f.write("\n")
    except Exception:
        _LOGGER.exception("Failed to append raw add log")


def _on_note_will_be_added(col, note, deck_id) -> None:
    cfg = get_config(reload=False)
    if not bool(cfg.get("enabled", True)):
        return

    source_mid = cfg.get("source_note_type_id")
    if source_mid is not None:
        try:
            if int(note.mid) != int(source_mid):
                return
        except Exception:
            return

    try:
        note_type_name = ""
        nt = note.note_type()
        if isinstance(nt, dict):
            note_type_name = str(nt.get("name") or "")
    except Exception:
        note_type_name = ""

    try:
        deck_name = col.decks.name(deck_id) or ""
    except Exception:
        deck_name = ""

    fields: dict[str, str] = {}
    try:
        for key in note.keys():
            fields[str(key)] = str(note[key] or "")
    except Exception:
        try:
            if isinstance(note.fields, list):
                fields = {f"ord_{idx}": str(val or "") for idx, val in enumerate(note.fields)}
        except Exception:
            fields = {}

    payload = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event": "note_will_be_added",
        "mid": int(note.mid),
        "note_type_name": note_type_name,
        "deck_id": int(deck_id),
        "deck_name": deck_name,
        "guid": str(note.guid or ""),
        "tags": [str(t) for t in (note.tags or [])],
        "fields": fields,
    }
    _append_raw_add_log(payload)
    _invalidate_widget_cache()
    if bool(cfg.get("run_on_card_added", False)):
        _schedule_card_added_run()


def _schedule_card_added_run() -> None:
    global _PENDING_CARD_ADDED_RUN
    if _PENDING_CARD_ADDED_RUN:
        return
    _PENDING_CARD_ADDED_RUN = True

    def _run() -> None:
        global _PENDING_CARD_ADDED_RUN
        _PENDING_CARD_ADDED_RUN = False
        run_conversion(manual=False)

    QTimer.singleShot(250, _run)


def _invalidate_widget_cache() -> None:
    global _WIDGET_CACHE_TS
    _WIDGET_CACHE_TS = 0.0


def _source_note_type_ids(cfg: dict[str, Any]) -> list[int]:
    out: list[int] = []
    sid = cfg.get("source_note_type_id")
    if sid is not None:
        try:
            out.append(int(sid))
        except Exception:
            pass
    if not out:
        for item in cfg.get("source_note_type_ids") or []:
            try:
                out.append(int(item))
            except Exception:
                continue
    return out


def _anki_quote(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def _count_unprocessed_now(cfg: dict[str, Any]) -> int:
    if mw is None or not getattr(mw, "col", None):
        return 0
    col = mw.col
    mids = _source_note_type_ids(cfg)
    if not mids:
        return 0
    tags_cfg = cfg.get("tags") or {}
    processed_tag = str(tags_cfg.get("processed_tag") or "").strip()
    if not processed_tag:
        return 0
    total = 0
    for mid in mids:
        try:
            model = col.models.get(int(mid))
        except Exception:
            model = None
        if not isinstance(model, dict):
            continue
        mname = str(model.get("name") or "").strip()
        if not mname:
            continue
        query = f'note:"{_anki_quote(mname)}" -tag:"{processed_tag}"'
        try:
            total += len(col.find_notes(query))
        except Exception:
            continue
    return int(total)


def _widget_cache_key(cfg: dict[str, Any]) -> str:
    mids = _source_note_type_ids(cfg)
    tag = str((cfg.get("tags") or {}).get("processed_tag") or "").strip()
    enabled = "1" if bool(cfg.get("enabled", True)) else "0"
    mids_raw = ",".join(str(x) for x in mids)
    return f"{enabled}|{mids_raw}|{tag}"


def _get_unprocessed_count(cfg: dict[str, Any]) -> int:
    global _WIDGET_CACHE_KEY, _WIDGET_CACHE_TS, _WIDGET_CACHE_UNPROCESSED
    key = _widget_cache_key(cfg)
    now = time.monotonic()
    if key == _WIDGET_CACHE_KEY and (now - _WIDGET_CACHE_TS) < _WIDGET_CACHE_TTL_SEC:
        return int(_WIDGET_CACHE_UNPROCESSED)
    value = _count_unprocessed_now(cfg)
    _WIDGET_CACHE_KEY = key
    _WIDGET_CACHE_TS = now
    _WIDGET_CACHE_UNPROCESSED = int(value)
    return int(value)


def _build_dashboard_widget_html(cfg: dict[str, Any]) -> str:
    unprocessed = _get_unprocessed_count(cfg)
    processed = int(_SESSION_PROCESSED)
    return (
        "<div class=\"stat-card\"><h3>AJpC Yomitran</h3>"
        f"<p>{html.escape(str(unprocessed))}&nbsp;/&nbsp;{html.escape(str(processed))}</p>"
        f"<p style=\"font-size:10px; \">waiting&nbsp;/&nbsp;done&nbsp;&nbsp;&nbsp;</p></div>"
    )


def _deck_browser_widget_hook(_deck_browser, content) -> None:
    try:
        cfg = get_config(reload=False)
        widget_html = _build_dashboard_widget_html(cfg)
        existing = getattr(content, "stats", "")
        content.stats = f"{existing}{widget_html}"
    except Exception:
        _LOGGER.exception("Failed to render Yomitran deck-browser widget")


def _is_global_sync_enabled() -> bool:
    if not bool(getattr(mw, "_ajpc_yomitran_host_settings_registered", False)):
        return True
    api = getattr(mw, "_ajpc_settings_api", None)
    if not isinstance(api, dict):
        return True
    getter = api.get("get_global_sync_enabled")
    if callable(getter):
        try:
            return bool(getter())
        except Exception:
            return True
    return True


def _is_global_debug_enabled() -> bool:
    if mw is None:
        return False
    api = getattr(mw, "_ajpc_settings_api", None)
    if not isinstance(api, dict):
        return False
    getter = api.get("get_global_debug_enabled")
    if callable(getter):
        try:
            return bool(getter())
        except Exception:
            return False
    return False


def on_sync_start(*_args, **_kwargs) -> None:
    cfg = get_config(reload=True)
    if not bool(cfg.get("run_on_sync", cfg.get("auto_on_sync", True))):
        return
    if not _is_global_sync_enabled():
        return
    run_conversion(manual=False)


def open_config_dialog(parent=None) -> None:
    cfg = get_config(reload=True)
    dlg = ConfigDialog(cfg, save_config, parent or mw)
    dlg.exec()


def build_external_settings(ctx):
    cfg = get_config(reload=True)
    panel = ConfigPanel(cfg, ctx.dlg)
    ctx.add_tab(panel, "Yomitran")

    state: dict[str, Any] = {"pending": None}

    def _validate(errors: list[str]) -> None:
        pending = panel.collect_config(errors)
        state["pending"] = pending

    def _save() -> None:
        pending = state.get("pending")
        if pending is None:
            pending = panel.collect_config([])
        if pending is None:
            raise RuntimeError("Yomitran settings are invalid.")
        save_config(pending)

    return {"validate": _validate, "save": _save}


def build_module_settings(ctx):
    cfg = get_config(reload=True)
    panel = ConfigPanel(cfg, ctx.dlg)
    ctx.add_tab(panel, "Yomitran")

    def _save(root_cfg: dict, errors: list[str]) -> None:
        pending = panel.collect_config(errors)
        if pending is None:
            return
        root_cfg["yomitran"] = pending

    return _save


def _menu_enabled() -> bool:
    cfg = get_config(reload=False)
    return bool(cfg.get("enabled", True))


def _install() -> None:
    if mw is None:
        return
    if getattr(mw, "_ajpc_yomitran_module_installed", False):
        return
    _cfg = get_config(reload=True)
    _LOGGER.info("Yomitran module initialized")
    if not is_available():
        _LOGGER.warning("pykakasi is not available. Hepburn conversion will fail when used.")
    gui_hooks.sync_will_start.append(on_sync_start)
    gui_hooks.deck_browser_will_render_content.append(_deck_browser_widget_hook)
    anki_hooks.note_will_be_added.append(_on_note_will_be_added)
    mw._ajpc_yomitran_module_installed = True


MODULE = ModuleSpec(
    id="yomitran",
    label="Yomitran",
    order=65,
    run_items=[
        {
            "label": "Run Yomitran",
            "callback": lambda: run_conversion(manual=True),
            "enabled_fn": _menu_enabled,
            "order": 60,
        },
    ],
    build_settings=build_module_settings,
    init=_install,
)
