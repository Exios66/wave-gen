"""wavegen command line.

  python -m wavegen analyze  REF.mov  -o out/analysis
  python -m wavegen build    --preset poolrooms --blend out/poolrooms.blend
  python -m wavegen still    --preset poolrooms --frame 120 -o out/still.png
  python -m wavegen render   --preset poolrooms -o out/frames [--frames 1-120]
  python -m wavegen audio    --preset poolrooms -o out/ambience.wav
  python -m wavegen post     out/frames -a out/ambience.wav -o out/poolrooms.mp4
  python -m wavegen make     --preset poolrooms -o out/poolrooms        (all of the above)
  python -m wavegen variants --preset poolrooms --seeds 1 2 3 -o out/variants

Common flags: --preview (fast low-res draft), --set key.path=value (repeatable).
Inside desktop Blender:  blender -b -P scripts/blender_run.py -- make --preset poolrooms
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import config

PREVIEW = [
    "render.percentage=50", "render.samples=16", "atmosphere.haze_density=0",
    "atmosphere.dust_count=90", "post.crf=22",
]


def _cfg(args) -> dict:
    over = list(PREVIEW if getattr(args, "preview", False) else []) + list(args.set or [])
    cfg = config.load(args.preset, over)
    if getattr(args, "seconds", None):
        cfg["render"]["seconds"] = args.seconds
    if getattr(args, "engine", None):
        cfg["render"]["engine"] = args.engine
    return cfg


def _frames(spec: str | None, cfg: dict) -> list[int] | None:
    from .frames import loop_frame_count, parse_frames
    try:
        return parse_frames(spec, loop_frame_count(cfg))
    except ValueError as e:
        raise SystemExit(f"wavegen: --frames: {e}") from None


def cmd_analyze(args):
    from .analyze import analyze
    res = analyze(args.video, args.out)
    print(json.dumps({k: res[k] for k in ("duration_s", "resolution", "brightness", "camera_motion", "audio")}, indent=2))
    print(f"palette: {' '.join(p['hex'] for p in res['palette'])}")
    print(f"wrote {args.out}/analysis.json, contact.jpg, palette_preset.json")


def cmd_build(args):
    from .scene import build_scene
    cfg = _cfg(args)
    build_scene(cfg, args.blend)
    print(f"saved {args.blend}")


def cmd_still(args):
    from .scene import build_scene, render_frames
    cfg = _cfg(args)
    build_scene(cfg, args.blend)
    out = Path(args.out)
    tmp = out.parent / f".{out.stem}_tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    [p] = render_frames(tmp, cfg, _frames(str(args.frame), cfg), overwrite=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(p), out.with_suffix(p.suffix))
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"wrote {out.with_suffix(p.suffix)}")


def cmd_render(args):
    from .scene import build_scene, render_frames
    cfg = _cfg(args)
    frames = _frames(args.frames, cfg)
    build_scene(cfg, args.blend)
    render_frames(args.out, cfg, frames, overwrite=args.overwrite)


def cmd_audio(args):
    from . import audio
    cfg = _cfg(args)
    if args.stems:
        for name, path in audio.write_stems(cfg, args.out).items():
            print(f"wrote {path}")
    else:
        print(f"wrote {audio.render(cfg, args.out)}")


def cmd_post(args):
    from . import post
    cfg = _cfg(args)
    print(f"wrote {post.assemble(args.frames_dir, args.out, cfg, args.audio)}")


def _make(cfg, out: Path, frames=None, blend=True, overwrite=False):
    from . import audio, post
    from .scene import build_scene, render_frames
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.json").write_text(json.dumps(cfg, indent=2))
    build_scene(cfg, out / f"{cfg['name']}.blend" if blend else None)
    render_frames(out / "frames", cfg, frames, overwrite=overwrite)
    if frames is not None:
        print(f"rendered a subset of frames; run `wavegen post {out / 'frames'}` once all of them exist")
        return
    wav = audio.render(cfg, out / "ambience.wav") if cfg["audio"]["enabled"] else None
    mp4 = post.assemble(out / "frames", out / f"{cfg['name']}.mp4", cfg, wav)
    print(f"wrote {mp4}")


def cmd_make(args):
    cfg = _cfg(args)
    _make(cfg, Path(args.out), _frames(args.frames, cfg), overwrite=args.overwrite)


def cmd_variants(args):
    from .scene import build_scene, render_frames
    base = _cfg(args)
    out = Path(args.out)
    for seed in args.seeds:
        cfg = config.mutate(base, seed, args.strength)
        d = out / cfg["name"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "config.json").write_text(json.dumps(cfg, indent=2))
        if args.full:
            _make(cfg, d)
        else:
            build_scene(cfg, d / f"{cfg['name']}.blend")
            render_frames(d / "frames", cfg, _frames(str(args.frame), cfg))
        print(f"variant {seed} -> {d}")


def cmd_loopcheck(args):
    from .scene import build_scene
    from .scene.loopcheck import driven_values, loop_mismatches
    cfg = _cfg(args)
    build_scene(cfg)
    bad = loop_mismatches(cfg)
    n = len(driven_values(1))
    if bad:
        print(f"loopcheck: {len(bad)} of {n} driven values do not loop:")
        for line in bad:
            print("  " + line)
        raise SystemExit(1)
    print(f"loopcheck: all {n} driven values match at the loop point")


def cmd_presets(args):
    for p in config.list_presets():
        print(p)


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(prog="wavegen", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, preset=True):
        if preset:
            p.add_argument("--preset", default="poolrooms", help="preset name or path to a .json")
        p.add_argument("--set", action="append", metavar="KEY=VALUE", help="override any config value")
        p.add_argument("--preview", action="store_true", help="fast low-res draft settings")
        p.add_argument("--seconds", type=float)
        p.add_argument("--engine", type=str.lower, choices=["cycles", "eevee"])

    p = sub.add_parser("analyze", help="analyse a reference video")
    p.add_argument("video")
    p.add_argument("-o", "--out", default="out/analysis")
    p.set_defaults(fn=cmd_analyze)

    p = sub.add_parser("build", help="build the scene and save a .blend")
    common(p)
    p.add_argument("--blend", default="out/scene.blend")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("still", help="render a single frame")
    common(p)
    p.add_argument("--frame", type=int, default=90)
    p.add_argument("--blend")
    p.add_argument("-o", "--out", default="out/still.png")
    p.set_defaults(fn=cmd_still)

    p = sub.add_parser("render", help="render frames")
    common(p)
    p.add_argument("--frames", help="e.g. 1-120 or 1,30,60")
    p.add_argument("--blend")
    p.add_argument("--overwrite", action="store_true", help="discard frames from a different config")
    p.add_argument("-o", "--out", default="out/frames")
    p.set_defaults(fn=cmd_render)

    p = sub.add_parser("audio", help="synthesize the ambient soundtrack")
    common(p)
    p.add_argument("--stems", action="store_true", help="write room/crt/bells/pad/bed/mix WAVs into the -o folder")
    p.add_argument("-o", "--out", default="out/ambience.wav")
    p.set_defaults(fn=cmd_audio)

    p = sub.add_parser("post", help="grade + encode frames (+audio) to mp4")
    common(p)
    p.add_argument("frames_dir")
    p.add_argument("-a", "--audio")
    p.add_argument("-o", "--out", default="out/wavegen.mp4")
    p.set_defaults(fn=cmd_post)

    p = sub.add_parser("make", help="build + render + audio + post in one go")
    common(p)
    p.add_argument("--frames")
    p.add_argument("--overwrite", action="store_true", help="discard frames from a different config")
    p.add_argument("-o", "--out", default="out/poolrooms")
    p.set_defaults(fn=cmd_make)

    p = sub.add_parser("variants", help="generate 'parallel' versions from seeds")
    common(p)
    p.add_argument("--seeds", type=int, nargs="+", required=True)
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--frame", type=int, default=90)
    p.add_argument("--full", action="store_true", help="render the full video for each variant")
    p.add_argument("-o", "--out", default="out/variants")
    p.set_defaults(fn=cmd_variants)

    p = sub.add_parser("loopcheck", help="verify every animated value returns to its start at the loop point")
    common(p)
    p.set_defaults(fn=cmd_loopcheck)

    p = sub.add_parser("presets", help="list bundled presets")
    p.set_defaults(fn=cmd_presets)

    args = ap.parse_args(argv)
    from .frames import StaleFramesError
    from .post import IncompleteLoopError
    try:
        args.fn(args)
    except (StaleFramesError, IncompleteLoopError) as e:
        raise SystemExit(f"wavegen: {e}") from None
    except ModuleNotFoundError as e:
        if e.name != "bpy":
            raise
        raise SystemExit(
            "wavegen: this command needs Blender 5.x. Either `pip install bpy` (Python 3.13), or run it "
            "inside desktop Blender:\n  blender -b -P scripts/blender_run.py -- " + " ".join(argv or sys.argv[1:])
        ) from None


if __name__ == "__main__":
    main(sys.argv[1:])
