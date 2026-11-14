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
    r.engine = rc["engine"]
    r.resolution_x, r.resolution_y = rc["resolution"]
    r.resolution_percentage = int(rc["percentage"])
    r.fps = int(rc["fps"])
    sc.frame_start = 1
    sc.frame_end = max(1, round(rc["seconds"] * rc["fps"]))
    r.use_motion_blur = False

    if rc["engine"] == "CYCLES":
        cy = sc.cycles
        cy.samples = int(rc["samples"])
        cy.use_adaptive_sampling = True
        cy.adaptive_threshold = 0.02
        cy.use_denoising = bool(rc["denoise"])
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
    """RenderLayers -> Bloom -> lens dispersion -> output (Blender 4.x & 5.x)."""
    sc = bpy.context.scene
    b, lens = cfg["render"]["bloom"], cfg["render"]["lens"]
    if hasattr(sc, "compositing_node_group"):  # 5.x node-group compositor
        ng = bpy.data.node_groups.new("WaveGenComp", "CompositorNodeTree")
        ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        sc.compositing_node_group = ng
        out = ng.nodes.new("NodeGroupOutput")
        out_socket = out.inputs[0]
    else:  # 4.x
        sc.use_nodes = True
        ng = sc.node_tree
        ng.nodes.clear()
        out = ng.nodes.new("CompositorNodeComposite")
        out_socket = out.inputs["Image"]
    rl = ng.nodes.new("CompositorNodeRLayers")
    glare = ng.nodes.new("CompositorNodeGlare")
    if "Type" in glare.inputs:  # 5.x: options are sockets
        glare.inputs["Type"].default_value = "Bloom"
        glare.inputs["Threshold"].default_value = b["threshold"]
        glare.inputs["Strength"].default_value = b["strength"]
        glare.inputs["Size"].default_value = b["size"]
    else:
        glare.glare_type = "BLOOM" if hasattr(glare, "glare_type") else "FOG_GLOW"
        glare.threshold = b["threshold"]
        _set(glare, "strength", b["strength"])
        _set(glare, "size", 8)
    ld = ng.nodes.new("CompositorNodeLensdist")
    if "Distortion" in ld.inputs:
        ld.inputs["Distortion"].default_value = lens["distortion"]
        ld.inputs["Dispersion"].default_value = lens["dispersion"]
        if "Fit" in ld.inputs:
            ld.inputs["Fit"].default_value = True
    ng.links.new(rl.outputs["Image"], glare.inputs["Image"])
    ng.links.new(glare.outputs["Image"], ld.inputs["Image"])
    ng.links.new(ld.outputs["Image"], out_socket)
    sc.render.use_compositing = True
