"""World light, volumetric haze, accent light and drifting dust motes."""
from __future__ import annotations

import math
import random

import bmesh
import bpy

from . import materials as M
from ..frames import loop_frame_count
from ..loop import cycles_for, periodic_expr
from .util import box, collection, drive, obj_from_bmesh


def build(cfg: dict, bounds) -> None:
    pal, at, li, fps = cfg["palette"], cfg["atmosphere"], cfg["lights"], cfg["render"]["fps"]
    x0, x1, y0, y1, h = bounds

    # world: soft pale-cyan ambience (the room reads as "lit from everywhere")
    world = bpy.data.worlds.get("Poolrooms") or bpy.data.worlds.new("Poolrooms")
    try:
        world.use_nodes = True
    except Exception:
        pass
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (*pal["world"], 1.0)
    bg.inputs["Strength"].default_value = li["world_strength"]
    bpy.context.scene.world = world

    # pink / lavender accent from off-screen left (tints the computer's flank)
    acc = bpy.data.lights.new("AccentLight", "AREA")
    acc.shape = "DISK"
    acc.size = 2.5
    acc.energy = li["accent_power"]
    acc.color = pal["accent_light"]
    ao = bpy.data.objects.new("AccentLight", acc)
    ao.location = (-3.2, -0.6, 1.6)
    ao.rotation_euler = (math.radians(88), 0, math.radians(-78))
    ao.visible_camera = False
    collection("Lights").objects.link(ao)

    col = collection("Atmosphere")
    if at["haze_density"] > 0:
        haze = box("Haze", (x0 + 0.05, y0 + 0.05, 0.02), (x1 - 0.05, y1 - 0.05, h - 0.05), col,
                   M.volume_haze("Haze", pal["haze"], at["haze_density"], at["haze_anisotropy"]))
        haze.visible_shadow = False

    # dust motes: one shared mesh, many linked duplicates, driver-animated
    n = int(at["dust_count"])
    if n <= 0:
        return
    rng = random.Random(cfg["seed"] * 7 + 1)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
    mesh_obj = obj_from_bmesh("Dust.proto", bm, col, None, smooth=True)
    mesh = mesh_obj.data
    bpy.data.objects.remove(mesh_obj)
    # emission strength varies per mote via Object Info > Random
    mat, nt, out = M._new("Dust")
    info = nt.nodes.new("ShaderNodeObjectInfo")
    rng_map = nt.nodes.new("ShaderNodeMapRange")
    rng_map.inputs["To Min"].default_value = at["dust_strength"][0]
    rng_map.inputs["To Max"].default_value = at["dust_strength"][1]
    nt.links.new(info.outputs["Random"], rng_map.inputs["Value"])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*pal["dust"], 1.0)
    nt.links.new(rng_map.outputs[0], em.inputs["Strength"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    mesh.materials.append(mat)

    cam = cfg["camera"]["location"]
    speed = at["dust_speed"]
    n_loop = loop_frame_count(cfg)
    for i in range(n):
        o = bpy.data.objects.new(f"Dust.{i:03d}", mesh)
        col.objects.link(o)
        s = rng.uniform(*at["dust_size"])
        o.scale = (s, s, s)
        o.visible_shadow = False
        # scatter in a wedge in front of the camera, denser close up
        dist = 0.5 + 6.0 * rng.random() ** 1.6
        ang = math.radians(rng.uniform(-42, 42))
        bx = cam[0] + math.sin(ang) * dist + 1.2 * dist / 6
        by = cam[1] + math.cos(ang) * dist
        bz = rng.uniform(0.3, 3.2)
        for axis, base, amp in ((0, bx, 0.35), (1, by, 0.25), (2, bz, 0.22)):
            period = rng.uniform(9, 24) / max(speed / 0.06, 1e-3)
            cyc = cycles_for(period, n_loop / fps)
            drive(o, "location", periodic_expr(base, amp, cyc, rng.uniform(0, 6.283), n_loop, 3), axis)
