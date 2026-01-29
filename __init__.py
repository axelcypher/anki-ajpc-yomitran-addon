from aqt import gui_hooks, mw
from aqt.qt import QAction
from aqt.utils import tooltip

from .config import DEFAULT_CONFIG, merge_config
from .conversion import convert_notes
from .ui import ConfigDialog

ADDON_NAME = mw.addonManager.addonFromModule(__name__) or __name__
_RUNNING = False


def get_config():
    cfg = mw.addonManager.getConfig(ADDON_NAME) or {}
    merged = merge_config(DEFAULT_CONFIG, cfg)
    if merged != cfg:
        mw.addonManager.writeConfig(ADDON_NAME, merged)
    return merged


def save_config(cfg):
    mw.addonManager.writeConfig(ADDON_NAME, cfg)


def open_config():
    cfg = get_config()
    dlg = ConfigDialog(cfg, save_config, mw)
    dlg.exec()


def run_conversion(manual: bool):
    global _RUNNING
    if _RUNNING:
        return
    _RUNNING = True
    try:
        convert_notes(get_config(), manual=manual)
    except Exception as exc:
        tooltip(f"Yomitan-Import Fehler: {exc}")
    finally:
        _RUNNING = False


def on_sync(_):
    cfg = get_config()
    if cfg.get("auto_on_sync"):
        run_conversion(manual=False)


def init_menu():
    menu = mw.form.menuTools.addMenu("AJpC")
    action_run = QAction("Yomitan-Import konvertieren", mw)
    action_run.triggered.connect(lambda: run_conversion(manual=True))
    menu.addAction(action_run)

    action_cfg = QAction("Yomitan-Import Einstellungen", mw)
    action_cfg.triggered.connect(open_config)
    menu.addAction(action_cfg)


init_menu()
gui_hooks.sync_did_finish.append(on_sync)
