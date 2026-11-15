"""Verify the built scene loops: every driven value at frame N+1 equals frame 1."""
from __future__ import annotations

import math

import bpy

from ..frames import loop_frame_count


def _driven_owners():
    seen = set()
    pools = [bpy.data.objects, bpy.data.materials, bpy.data.worlds, bpy.data.node_groups,
             bpy.data.cameras, bpy.data.lights, bpy.data.meshes]
    for pool in pools:
        for idb in pool:
            for owner in (idb, getattr(idb, "node_tree", None)):
                if owner is None or id(owner) in seen:
                    continue
                seen.add(id(owner))
                ad = getattr(owner, "animation_data", None)
                if ad and ad.drivers:
                    yield owner


def driven_values(frame: int) -> dict[str, float]:
    sc = bpy.context.scene
    sc.frame_set(frame)
    out = {}
    for owner in _driven_owners():
        for fc in owner.animation_data.drivers:
            val = owner.path_resolve(fc.data_path)
            try:
                val = val[fc.array_index]
            except TypeError:
                pass
            out[f"{owner.name}:{fc.data_path}[{fc.array_index}]"] = float(val)
    return out


def loop_mismatches(cfg: dict, tol: float = 1e-5) -> list[str]:
    """Return a line for each driven value that differs between frame 1 and N+1.

    Rotations are compared modulo a full turn (a spin of k turns is seamless).
    """
    n = loop_frame_count(cfg)
    a, b = driven_values(1), driven_values(n + 1)
    bad = []
    for key, va in a.items():
        vb = b[key]
        d = vb - va
        if "rotation" in key:
            d = math.remainder(d, 2 * math.pi)
        if abs(d) > tol:
            bad.append(f"{key}: frame 1 = {va:.6f}, frame {n + 1} = {vb:.6f}")
    bpy.context.scene.frame_set(1)
    return bad
