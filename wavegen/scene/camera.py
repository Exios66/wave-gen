"""Slow, floating camera with a parallax sweep: a dolly and a look-at target that each drift on
smooth sines with a whole number of cycles per loop, so the video loops seamlessly."""
from __future__ import annotations

import bpy

from .focus import resolve_focus
from ..frames import loop_frame_count
from ..loop import cycles_for, periodic_expr
from .util import collection, drive


def build(cfg: dict, focus_obj=None) -> bpy.types.Object:
    cc = cfg["camera"]
    n = loop_frame_count(cfg)
    loop_s = n / cfg["render"]["fps"]
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
    sw = cc.get("sweep") or {"amplitude": [0, 0, 0], "target_amplitude": [0, 0, 0], "cycles": 1}
    for i in range(3):
        # parallax sweep: camera and target swing together (same phase) once per loop, eased by the
        # second harmonic, so the CRT holds its place while the room slides behind it
        cam_sweep = periodic_expr(0.0, sw["amplitude"][i], sw["cycles"], 0.0, n)
        tgt_sweep = periodic_expr(0.0, sw["target_amplitude"][i], sw["cycles"], 0.0, n)
        drive(cam, "location", periodic_expr(cc["location"][i], d["amplitude"][i],
                                             cycles_for(d["period"][i], loop_s), 0.7 * i + 0.3, n)
              + " + " + cam_sweep, i)
        drive(target, "location", periodic_expr(cc["target"][i], d["target_amplitude"][i],
                                                cycles_for(d["target_period"][i], loop_s), 1.3 * i + 2.0, n)
              + " + " + tgt_sweep, i)
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
