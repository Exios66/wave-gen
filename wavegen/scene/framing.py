"""Where scene objects land in the camera frame (for composition tests and tuning)."""
from __future__ import annotations

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


def project_bounds(name: str, frame: int = 1) -> tuple[float, float, float, float]:
    """``(x0, x1, y0, y1)`` of an object's bounding box in frame fractions; y runs from the top."""
    sc = bpy.context.scene
    sc.frame_set(frame)
    o = bpy.data.objects[name]
    pts = [world_to_camera_view(sc, sc.camera, o.matrix_world @ Vector(c)) for c in o.bound_box]
    xs = [p.x for p in pts]
    ys = [1 - p.y for p in pts]
    return min(xs), max(xs), min(ys), max(ys)
