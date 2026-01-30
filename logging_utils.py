import logging
import os

_LOGGER = logging.getLogger("ajpc_yomitran")


def get_logger() -> logging.Logger:
    return _LOGGER


def configure_logging(cfg: dict):
    # Clear previous handlers to allow live reconfiguration
    for handler in list(_LOGGER.handlers):
        _LOGGER.removeHandler(handler)

    debug_cfg = (cfg or {}).get("debug") or {}
    enabled = bool(debug_cfg.get("enabled", False))
    if not enabled:
        _LOGGER.addHandler(logging.NullHandler())
        _LOGGER.setLevel(logging.CRITICAL)
        _LOGGER.propagate = False
        return

    path = debug_cfg.get("path") or "ajpc-yomitran.log"
    if not os.path.isabs(path):
        base_dir = os.path.dirname(__file__)
        path = os.path.join(base_dir, path)

    _LOGGER.setLevel(logging.DEBUG)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    handler.setFormatter(formatter)
    _LOGGER.addHandler(handler)
    _LOGGER.propagate = False
    _LOGGER.info("Debug logging enabled")
