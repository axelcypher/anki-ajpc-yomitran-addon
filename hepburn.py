import os
import sys


# Prefer vendored dependencies so users don't need to install anything.
_VENDOR_DIR = os.path.join(os.path.dirname(__file__), "vendor")
if os.path.isdir(_VENDOR_DIR) and _VENDOR_DIR not in sys.path:
    sys.path.insert(0, _VENDOR_DIR)

try:
    from pykakasi import kakasi as _kakasi  # type: ignore
except Exception:  # pragma: no cover - external dependency
    _kakasi = None


def is_available() -> bool:
    return _kakasi is not None


def to_hepburn(text: str) -> str:
    if not text:
        return ""
    if _kakasi is None:
        raise RuntimeError(
            "pykakasi is not available. The bundled copy may be missing or broken. "
            "Hepburn conversion is unavailable."
        )

    conv = _kakasi()
    conv.setMode("H", "a")
    conv.setMode("K", "a")
    conv.setMode("J", "a")
    conv.setMode("r", "Hepburn")
    converter = conv.getConverter()
    return converter.do(text)
