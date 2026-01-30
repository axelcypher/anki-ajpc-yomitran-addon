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
            "pykakasi is not installed. Install it in Anki's Python environment "
            "to enable proper Hepburn conversion."
        )

    conv = _kakasi()
    conv.setMode("H", "a")
    conv.setMode("K", "a")
    conv.setMode("J", "a")
    conv.setMode("r", "Hepburn")
    converter = conv.getConverter()
    return converter.do(text)
