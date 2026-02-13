from __future__ import annotations

import os

from aqt import gui_hooks, mw
from aqt.qt import QAction

from .modules import discover_modules, iter_run_items
from .modules import yomitran as yomitran_module


_SETTINGS_PROVIDER_ID = "ajpc-yomitran"
_SIDEBAR_HOOKED = False
_HIDE_CONFIG_FOR_ADDONS = {"ajpc-yomitran_dev", "ajpc-tools_dev"}


def _open_config_action() -> None:
    yomitran_module.open_config_dialog(mw)


def _noop_addon_config_action() -> bool:
    # Prevent Anki's built-in JSON config editor for AJpC add-ons.
    return True


def _on_addons_dialog_selection(dialog, addon_meta) -> None:
    try:
        dir_name = str(getattr(addon_meta, "dir_name", "") or "")
        if dir_name in _HIDE_CONFIG_FOR_ADDONS:
            dialog.form.config.setEnabled(False)
    except Exception:
        return


def _install_addons_dialog_config_guard() -> None:
    if mw is None or not getattr(mw, "addonManager", None):
        return
    mgr = mw.addonManager
    for addon_name in _HIDE_CONFIG_FOR_ADDONS:
        try:
            mgr.setConfigAction(addon_name, _noop_addon_config_action)
        except Exception:
            continue
    if not getattr(mw, "_ajpc_addons_cfg_guard_installed", False):
        gui_hooks.addons_dialog_did_change_selected_addon.append(_on_addons_dialog_selection)
        mw._ajpc_addons_cfg_guard_installed = True


def _register_host_settings_provider() -> bool:
    api = getattr(mw, "_ajpc_settings_api", None)
    if not isinstance(api, dict):
        return False

    version = str(api.get("version") or "").strip()
    if version and not version.startswith("1."):
        return False

    register = api.get("register")
    if not callable(register):
        return False

    try:
        return bool(
            register(
                provider_id=_SETTINGS_PROVIDER_ID,
                label="Yomitran",
                build_settings=yomitran_module.build_external_settings,
                order=65,
            )
        )
    except Exception:
        return False


def _init_menu(modules) -> None:
    if mw is None:
        return

    run_items = iter_run_items(modules)
    host_settings_registered = _register_host_settings_provider()
    setattr(mw, "_ajpc_yomitran_host_settings_registered", bool(host_settings_registered))

    api = getattr(mw, "_ajpc_menu_api", None)
    if isinstance(api, dict):
        register = api.get("register")
        if callable(register):
            for item in run_items:
                cb = item.get("callback")
                if not callable(cb):
                    continue
                register(
                    kind="run",
                    label=str(item.get("label") or "Run Yomitran"),
                    callback=cb,
                    enabled_fn=item.get("enabled_fn"),
                    visible_fn=item.get("visible_fn"),
                    order=int(item.get("order", 100)),
                )
            if not host_settings_registered:
                register(
                    kind="settings",
                    label="Yomitran Settings",
                    callback=_open_config_action,
                    order=65,
                )
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
        action_run.triggered.connect(lambda: yomitran_module.run_conversion(manual=True))
        menu.addAction(action_run)

    if not host_settings_registered and "Yomitran Settings" not in existing:
        action_cfg = QAction("Yomitran Settings", mw)
        action_cfg.triggered.connect(_open_config_action)
        menu.addAction(action_cfg)


def _init_onigiri_sidebar() -> None:
    global _SIDEBAR_HOOKED
    if _SIDEBAR_HOOKED:
        return
    try:
        import Onigiri
    except Exception:
        return

    try:
        icon_svg = ""
        icon_path = os.path.join(os.path.dirname(__file__), "yomitan-icon.svg")
        if os.path.exists(icon_path):
            with open(icon_path, "r", encoding="utf-8") as f:
                icon_svg = f.read()

        Onigiri.register_sidebar_action(
            entry_id="ajpc-yomitran.settings",
            label="Yomitran Settings",
            command="ajpc_yomitran_open_settings",
            icon_svg=icon_svg,
        )

        def _on_js(handled, cmd, context):
            if cmd == "ajpc_yomitran_open_settings":
                yomitran_module.open_config_dialog(mw)
                return (True, None)
            return handled

        gui_hooks.webview_did_receive_js_message.append(_on_js)
        _SIDEBAR_HOOKED = True
    except Exception:
        return


def _bootstrap() -> None:
    if mw is None:
        return
    _install_addons_dialog_config_guard()
    first_boot = not bool(getattr(mw, "_ajpc_yomitran_bootstrapped", False))

    if first_boot:
        modules = discover_modules()
        for mod in modules:
            if callable(mod.init):
                try:
                    mod.init()
                except Exception:
                    continue
        _init_onigiri_sidebar()
    else:
        modules = discover_modules()

    _init_menu(modules)
    mw._ajpc_yomitran_bootstrapped = True


def _on_profile_open(*_args, **_kwargs):
    _bootstrap()


_bootstrap()
gui_hooks.profile_did_open.append(_on_profile_open)


# Backward-compatible exports
get_config = yomitran_module.get_config
save_config = yomitran_module.save_config
open_config = lambda: yomitran_module.open_config_dialog(mw)
run_conversion = yomitran_module.run_conversion
