"""Slow, floating camera: a dolly that drifts on incommensurate sines and a
look-at target that wanders independently, so the move never visibly loops."""
from __future__ import annotations

import bpy

from .focus import resolve_focus
from .util import collection, drift_expr, drive


def build(cfg: dict, focus_obj=None) -> bpy.types.Object:
    cc, fps = cfg["camera"], cfg["render"]["fps"]
    col = collection("Camera")
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = cc["lens"]
    cam_data.sensor_width = 36.0
    cam_data.clip_start = 0.02
    cam_data.clip_end = 200.0
    cam = bpy.data.objects.new("Camera", cam_data)
    col.objects.link(cam)
    target = bpy.data.objects.new("Camera.target", None)
    col.objects.link(target)

    d = cc["drift"]
    for i in range(3):
        drive(cam, "location", drift_expr(cc["location"][i], d["amplitude"][i], d["period"][i], 0.7 * i + 0.3, fps), i)
        drive(target, "location", drift_expr(cc["target"][i], d["target_amplitude"][i], d["target_period"][i], 1.3 * i + 2.0, fps), i)
    track = cam.constraints.new("TRACK_TO")
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    if cc["dof"]:
        cam_data.dof.use_dof = True
        cam_data.dof.aperture_fstop = cc["fstop"]
        kind, dist = resolve_focus(cc["focus_on"], focus_obj is not None)
        if kind == "object":
            cam_data.dof.focus_object = focus_obj
        elif kind == "target":
            cam_data.dof.focus_object = target
        else:
            cam_data.dof.focus_distance = dist
    bpy.context.scene.camera = cam
    return cam
