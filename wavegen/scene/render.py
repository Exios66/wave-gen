"""Engine, colour management and an in-Blender compositor (bloom + lens)."""
from __future__ import annotations

import bpy


def _set(obj, attr, value):
    try:
        setattr(obj, attr, value)
        return True
    except (AttributeError, TypeError, ValueError):
        return False


def _pick_gpu(prefs) -> bool:
    for backend in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            prefs.compute_device_type = backend
            prefs.get_devices()
            devs = [d for d in prefs.devices if d.type == backend]
            if devs:
                for d in devs:
                    d.use = True
                return True
        except Exception:
            continue
    return False


def configure(cfg: dict) -> None:
    sc = bpy.context.scene
    rc = cfg["render"]
    r = sc.render
    from .engine import resolve_engine
    engine = resolve_engine(rc["engine"], tuple(bpy.app.version))
    r.engine = engine
    r.resolution_x, r.resolution_y = rc["resolution"]
    r.resolution_percentage = int(rc["percentage"])
    r.fps = int(rc["fps"])
    sc.frame_start = 1
    sc.frame_end = max(1, round(rc["seconds"] * rc["fps"]))
    mb = float(rc.get("motion_blur", 0.0))
    r.use_motion_blur = mb > 0
    if mb > 0:
        r.motion_blur_shutter = mb

    if engine == "CYCLES":
        cy = sc.cycles
        cy.samples = int(rc["samples"])
        cy.use_adaptive_sampling = True
        cy.adaptive_threshold = 0.02
        cy.use_denoising = bool(rc["denoise"])
        cy.use_animated_seed = False      # same noise pattern every frame: no grain boil
        cy.seed = 0
        _set(cy, "denoiser", "OPENIMAGEDENOISE")
        cy.max_bounces = int(rc["max_bounces"])
        cy.transmission_bounces = 8
        cy.volume_bounces = 1
        cy.volume_step_rate = 4.0
        cy.caustics_reflective = False
        cy.caustics_refractive = False
        cy.sample_clamp_indirect = 8.0
        cy.light_sampling_threshold = 0.01
        cy.device = "CPU"
        if rc["device"] in ("AUTO", "GPU"):
            try:
                prefs = bpy.context.preferences.addons["cycles"].preferences
                if _pick_gpu(prefs):
                    cy.device = "GPU"
            except Exception:
                pass
        r.use_persistent_data = True
    else:  # EEVEE
        ee = sc.eevee
        _set(ee, "taa_render_samples", int(rc["samples"]))
        _set(ee, "use_raytracing", True)
        _set(ee, "ray_tracing_method", "SCREEN")
        _set(ee, "use_shadows", True)
        _set(ee, "volumetric_tile_size", "4")
        _set(ee, "volumetric_samples", 96)
        _set(ee, "use_volumetric_shadows", True)
        _set(ee, "use_gtao", True)
        _set(ee, "use_fast_gi", True)

    vs = sc.view_settings
    _set(vs, "view_transform", rc["view_transform"])
    _set(vs, "look", rc["look"])
    vs.exposure = rc["exposure"]
    vs.gamma = rc["gamma"]

    r.image_settings.file_format = rc["format"]
    _set(r.image_settings, "color_depth", "16" if rc["format"] == "PNG" else "8")
    _set(r.image_settings, "compression", 30)
    _compositor(cfg)


def _compositor(cfg: dict) -> None:
    """RenderLayers -> Bloom (skipped at strength 0) -> lens dispersion -> output (Blender 5.x)."""
    sc = bpy.context.scene
    b, lens = cfg["render"]["bloom"], cfg["render"]["lens"]
    ng = bpy.data.node_groups.new("WaveGenComp", "CompositorNodeTree")
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    sc.compositing_node_group = ng
    out_socket = ng.nodes.new("NodeGroupOutput").inputs[0]
    rl = ng.nodes.new("CompositorNodeRLayers")
    ld = ng.nodes.new("CompositorNodeLensdist")
    ld.inputs["Distortion"].default_value = lens["distortion"]
    ld.inputs["Dispersion"].default_value = lens["dispersion"]
    ld.inputs["Fit"].default_value = True
    ng.links.new(ld.outputs["Image"], out_socket)
    sc.render.use_compositing = True
    if b["strength"] <= 0:
        ng.links.new(rl.outputs["Image"], ld.inputs["Image"])
        return
    glare = ng.nodes.new("CompositorNodeGlare")
    glare.inputs["Type"].default_value = "Bloom"
    glare.inputs["Threshold"].default_value = b["threshold"]
    glare.inputs["Strength"].default_value = b["strength"]
    glare.inputs["Size"].default_value = b["size"]
    ng.links.new(rl.outputs["Image"], glare.inputs["Image"])
    ng.links.new(glare.outputs["Image"], ld.inputs["Image"])
