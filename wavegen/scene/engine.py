"""Render-engine id resolution and the Blender version gate (no bpy)."""
from __future__ import annotations

_ENGINES = {"cycles": "CYCLES", "eevee": "BLENDER_EEVEE", "blender_eevee": "BLENDER_EEVEE",
            "blender_eevee_next": "BLENDER_EEVEE"}


def resolve_engine(name: str, version: tuple[int, int, int]) -> str:
    if tuple(version) < (5, 0, 0):
        raise RuntimeError(f"wave-gen needs Blender 5.x (found {'.'.join(map(str, version))})")
    try:
        return _ENGINES[str(name).lower()]
    except KeyError:
        raise ValueError(f"render.engine={name!r}; use 'cycles' or 'eevee'") from None
