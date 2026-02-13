from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
import os
import pkgutil
from typing import Callable, Iterable


@dataclass
class ModuleSpec:
    id: str
    label: str
    order: int = 100
    run_items: list[dict] = field(default_factory=list)
    settings_items: list[dict] = field(default_factory=list)
    init: Callable[[], None] | None = None
    build_settings: Callable[[object], Callable[[dict, list[str]], None] | None] | None = None


def discover_modules() -> list[ModuleSpec]:
    modules: list[ModuleSpec] = []
    pkg_path = os.path.dirname(__file__)
    for mod in pkgutil.iter_modules([pkg_path]):
        if mod.name.startswith("_"):
            continue
        try:
            m = import_module(f"{__name__}.{mod.name}")
        except Exception:
            continue
        spec = getattr(m, "MODULE", None)
        if isinstance(spec, ModuleSpec):
            modules.append(spec)
    modules.sort(key=lambda m: (int(m.order), str(m.label)))
    return modules


def iter_run_items(modules: Iterable[ModuleSpec]) -> list[dict]:
    items: list[dict] = []
    for mod in modules:
        items.extend(mod.run_items or [])
    return items


def iter_settings_items(modules: Iterable[ModuleSpec]) -> list[dict]:
    items: list[dict] = []
    for mod in modules:
        items.extend(mod.settings_items or [])
    return items
