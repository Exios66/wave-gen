"""wavegen command line.

  python -m wavegen analyze  REF.mov  -o out/analysis
  python -m wavegen build    --preset poolrooms --blend out/poolrooms.blend
  python -m wavegen still    --preset poolrooms --frame 120 -o out/still.png
  python -m wavegen render   --preset poolrooms -o out/frames [--frames 1-120]
  python -m wavegen audio    --preset poolrooms --stems -o out/stems
  python -m wavegen post     out/frames --stems out/stems -o out/poolrooms.mp4 [--audio-mix full]
  python -m wavegen make     --preset poolrooms -o out/poolrooms        (all of the above)
  python -m wavegen extend   out/poolrooms/poolrooms.mp4 --duration 1h -o out/poolrooms_1h.mp4
  python -m wavegen loopcheck --preset poolrooms
  python -m wavegen variants --preset poolrooms --seeds 1 2 3 -o out/variants
  python -m wavegen presets  [list | show NAME [--resolved|--lineage]]
  python -m wavegen presets save rose_room --from poolrooms --set palette.water=[0.8,0.78,0.98] --tags pink,day
  python -m wavegen presets catalog          # docs/PRESETS.md + a thumbnail per preset
  python -m wavegen presets save keeper --from poolrooms --config out/variants/poolrooms-v3/config.json

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
    if getattr(args, "seconds", None) is not None:
        cfg["render"]["seconds"] = args.seconds
    if getattr(args, "engine", None):
        cfg["render"]["engine"] = args.engine
    from .frames import loop_frame_count
    try:
        loop_frame_count(cfg)
    except (TypeError, ValueError) as e:
        raise SystemExit(f"wavegen: {e}") from None
    return cfg


def _seconds(text: str) -> float:
    import math
    try:
        v = float(text)
    except ValueError:
        v = math.nan
    if not (math.isfinite(v) and v > 0):
        raise argparse.ArgumentTypeError(f"{text!r} is not a loop length above zero")
    return v


def lookdev_sets(user_sets: list[str] | None) -> list[str]:
    """Lookdev overrides: small and quick by default, and always a PNG still (the grade reads PNGs)."""
    return ["render.resolution=[960,540]", "render.samples=48"] + list(user_sets or []) + ['render.format="PNG"']


def post_hint(out: Path) -> str:
    """How to finish a run that rendered only some frames, with the exact config it used."""
    import shlex
    frames, preset, mp4 = (shlex.quote(str(out / name)) for name in ("frames", "config.json", "loop.mp4"))
    return (f"rendered a subset of frames; once all of them exist run "
            f"`wavegen post {frames} --preset {preset} -o {mp4}`")


def _frames(spec: str | None, cfg: dict) -> list[int] | None:
    from .frames import loop_frame_count, parse_frames
    try:
        return parse_frames(spec, loop_frame_count(cfg))
    except ValueError as e:
        raise SystemExit(f"wavegen: --frames: {e}") from None


def _default_frame(frame: int | None, cfg: dict) -> int:
    """An explicit frame is kept (and validated later); the default stays inside short loops."""
    from .frames import loop_frame_count
    return frame if frame is not None else min(90, loop_frame_count(cfg))


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
    [p] = render_frames(tmp, cfg, _frames(str(_default_frame(args.frame, cfg)), cfg), overwrite=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(p), out.with_suffix(p.suffix))
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"wrote {out.with_suffix(p.suffix)}")


def cmd_lookdev(args):
    """Render a still (960x540, 48 samples unless overridden) and compare it with a reference."""
    import json
    from . import lookdev
    sets = lookdev_sets(args.set)
    out = Path(args.out)
    still = out.with_suffix(".png")
    cmd_still(argparse.Namespace(**{**vars(args), "set": sets, "out": str(still), "blend": None}))
    cfg = _cfg(argparse.Namespace(**{**vars(args), "set": sets}))
    graded = out.with_name(out.stem + "_graded.png")    # judge what ships: the post-processed frame
    lookdev.grade_still(still, graded, cfg)            # (post.grade alone toggles the colour grade)
    still = graded
    r = lookdev.compare(still, Path(args.ref), out.with_suffix(".jpg"))
    summary = {k: v for k, v in r.items() if not k.startswith("palette_r")}
    out.with_suffix(".json").write_text(json.dumps(r, indent=2))
    print(json.dumps(summary, indent=2))
    print(f"wrote {out.with_suffix('.jpg')}")


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
    print(f"wrote {post.assemble(args.frames_dir, args.out, cfg, args.stems, args.audio_mix)}")


def _make(cfg, out: Path, frames=None, blend=True, overwrite=False, audio_mix="bed"):
    from . import audio, post
    from .scene import build_scene, render_frames
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.json").write_text(json.dumps(cfg, indent=2))
    build_scene(cfg, out / f"{cfg['name']}.blend" if blend else None)
    render_frames(out / "frames", cfg, frames, overwrite=overwrite)
    if frames is not None:
        print(post_hint(out))
        return
    stems = out / "stems"
    if cfg["audio"]["enabled"]:
        audio.write_stems(cfg, stems)
    mp4 = post.assemble(out / "frames", out / f"{cfg['name']}.mp4", cfg,
                        stems if cfg["audio"]["enabled"] else None, audio_mix)
    print(f"wrote {mp4}")


def cmd_make(args):
    cfg = _cfg(args)
    _make(cfg, Path(args.out), _frames(args.frames, cfg), overwrite=args.overwrite, audio_mix=args.audio_mix)


def cmd_extend(args):
    from . import post
    try:
        seconds = post.parse_duration(args.duration)
    except ValueError as e:
        raise SystemExit(f"wavegen: --duration: {e}") from None
    stems = Path(args.stems) if args.stems else Path(args.loop).parent / "stems"
    print(f"wrote {post.extend(args.loop, stems, seconds, args.out, args.audio_mix)}")


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
            render_frames(d / "frames", cfg, _frames(str(_default_frame(args.frame, cfg)), cfg))
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


def cmd_presets_list(args):
    names = config.list_presets()
    if getattr(args, "names", False):
        print("\n".join(names))
        return
    print(f"{'NAME':<24} {'EXTENDS':<20} {'TAGS':<26} DESCRIPTION")
    print("-" * 100)
    for n in names:
        i = config.preset_info(n)
        print(f"{n:<24} {i['extends'] or '-':<20} {','.join(i['tags']) or '-':<26} {i['description']}")


def cmd_presets_show(args):
    if args.lineage:
        print(" -> ".join(config.lineage(args.name)))
    elif args.resolved:
        print(json.dumps(config.load(args.name), indent=2))
    else:
        print(config.find_preset(args.name).read_text().rstrip())


CATALOG_SETS = ["render.resolution=[480,270]", "render.samples=32", 'render.format="PNG"']


def cmd_presets_catalog(args):
    """Write PRESETS.md and (unless --no-render) a graded thumbnail per preset beside it."""
    import subprocess
    from . import catalog, lookdev
    out = Path(args.out)
    thumbs = out / "presets"
    thumbs.mkdir(parents=True, exist_ok=True)
    ents = catalog.entries()
    if not args.no_render:
        for e in ents:
            still = thumbs / f"{e['name']}.png"
            ns = argparse.Namespace(preset=e["name"], set=CATALOG_SETS, frame=None, out=str(still),
                                    blend=None, preview=False, seconds=None, engine=None)
            cmd_still(ns)
            graded = lookdev.grade_still(still, thumbs / f"{e['name']}_graded.png", _cfg(ns))
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(graded), "-q:v", "3",
                            str(thumbs / f"{e['name']}.jpg")], check=True)
            still.unlink(missing_ok=True)
            Path(graded).unlink(missing_ok=True)
    have = {e["name"] for e in ents if (thumbs / f"{e['name']}.jpg").is_file()}
    (out / "PRESETS.md").write_text(catalog.markdown(ents, "presets", have))
    print(f"wrote {out / 'PRESETS.md'} ({len(ents)} presets)")


def _parent_ref(parent: Path, dest: Path, name: str) -> str:
    """How the saved preset should name its parent: by name when that finds the same file
    from the destination folder, else by its full path. A preset that shadows its parent's
    name always uses the path, since the name would find the preset itself."""
    try:
        if parent.stem != name and config.find_preset(parent.stem, near=dest).resolve() == parent.resolve():
            return parent.stem
    except FileNotFoundError:
        pass
    return str(parent.resolve())


def cmd_presets_save(args):
    name = args.name
    if not name or Path(name).name != name or name.endswith(".json"):
        raise SystemExit(f"wavegen: preset name must be a plain name like 'rose_room', got {name!r}")
    try:
        parent = config.find_preset(args.parent)
        base = config.load(args.parent)
        target = config.load(args.config if args.config else args.parent, args.set)
    except (FileNotFoundError, ValueError) as e:
        raise SystemExit(f"wavegen: {e}") from None
    bad = config.unknown_keys(target, config.DEFAULTS)
    if bad:
        raise SystemExit(f"wavegen: the config does not have {', '.join(bad)}; nothing saved")
    dest = Path(args.dir) if args.dir else config.library_dirs()[0]
    path = dest / f"{name}.json"
    if not args.force:
        try:
            existing = path if path.exists() else config.find_preset(name)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            raise SystemExit(f"wavegen: preset '{name}' already exists at {existing}; "
                             f"pick another name or pass --force to replace or shadow it")
    strip = lambda c: {k: v for k, v in c.items() if k != "name"}   # noqa: E731
    body = {"name": name, "extends": _parent_ref(parent, dest, name)}
    if args.description:
        body["description"] = args.description
    if args.tags:
        body["tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]
    body.update(config.diff_config(strip(target), strip(base)))
    dest.mkdir(parents=True, exist_ok=True)
    old = path.read_text() if path.exists() else None
    text = json.dumps(body, indent=2) + "\n"
    try:                                       # without --force, never replace a file another save just wrote
        with open(path, "w" if args.force else "x") as f:
            f.write(text)
    except FileExistsError:
        raise SystemExit(f"wavegen: preset '{name}' already exists at {path}; "
                         f"pick another name or pass --force to replace it") from None
    try:                                       # the saved preset must rebuild the same config
        ok = strip(config.load(str(path))) == strip(target)
        why = "would not reproduce the config"
    except (ValueError, FileNotFoundError) as e:
        ok, why = False, f"would not load ({e})"
    if not ok:
        path.write_text(old) if old is not None else path.unlink()
        raise SystemExit(f"wavegen: saving {name} {why}; nothing saved")
    changed = len(body) - 2 - ("description" in body) - ("tags" in body)
    print(f"saved {path} (extends {body['extends']}, {changed} changed section{'s' if changed != 1 else ''})")


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(prog="wavegen", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, preset=True):
        if preset:
            p.add_argument("--preset", default="poolrooms", help="preset name or path to a .json")
        p.add_argument("--set", action="append", metavar="KEY=VALUE", help="override any config value")
        p.add_argument("--preview", action="store_true", help="fast low-res draft settings")
        p.add_argument("--seconds", type=_seconds, help="loop length, above zero")
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
    p.add_argument("--frame", type=int, help="default: 90, or the last frame of a shorter loop")
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
    p.add_argument("--stems", help="folder with bed.wav / mix.wav (from `wavegen audio --stems`)")
    p.add_argument("--audio-mix", choices=["bed", "full"], default="bed",
                   help="bed = room + crt ambience (default, leaves room for your music); full = with pad and bells")
    p.add_argument("-o", "--out", default="out/wavegen.mp4")
    p.set_defaults(fn=cmd_post)

    p = sub.add_parser("make", help="build + render + audio + post in one go")
    common(p)
    p.add_argument("--frames")
    p.add_argument("--overwrite", action="store_true", help="discard frames from a different config")
    p.add_argument("--audio-mix", choices=["bed", "full"], default="bed")
    p.add_argument("-o", "--out", default="out/poolrooms")
    p.set_defaults(fn=cmd_make)

    p = sub.add_parser("extend", help="repeat a finished loop to a long video (e.g. 1h) without re-encoding video")
    p.add_argument("loop", help="loop .mp4 from `make`/`post`")
    p.add_argument("--duration", required=True, help="e.g. 1h, 90m, 1h30m")
    p.add_argument("--stems", help="stems folder (default: <loop folder>/stems)")
    p.add_argument("--audio-mix", choices=["bed", "full"], default="bed")
    p.add_argument("-o", "--out", required=True)
    p.set_defaults(fn=cmd_extend)

    p = sub.add_parser("variants", help="generate 'parallel' versions from seeds")
    common(p)
    p.add_argument("--seeds", type=int, nargs="+", required=True)
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--frame", type=int, help="default: 90, or the last frame of a shorter loop")
    p.add_argument("--full", action="store_true", help="render the full video for each variant")
    p.add_argument("-o", "--out", default="out/variants")
    p.set_defaults(fn=cmd_variants)

    p = sub.add_parser("lookdev", help="render a still and compare it side by side with a reference frame")
    common(p)
    p.add_argument("--frame", type=int, default=1)
    p.add_argument("--ref", default="docs/ref/video/v50.jpg")
    p.add_argument("-o", "--out", default="out/lookdev/still")
    p.set_defaults(fn=cmd_lookdev)

    p = sub.add_parser("loopcheck", help="verify every animated value returns to its start at the loop point")
    common(p)
    p.set_defaults(fn=cmd_loopcheck)

    p = sub.add_parser("presets", help="list, show and save presets (your library: WAVEGEN_PRESET_PATH)")
    p.set_defaults(fn=cmd_presets_list, names=False)
    ps = p.add_subparsers(dest="presets_cmd")
    q = ps.add_parser("list", help="every preset with its parent, tags and description")
    q.add_argument("--names", action="store_true", help="names only, one per line")
    q.set_defaults(fn=cmd_presets_list)
    q = ps.add_parser("show", help="print a preset as written (or --resolved / --lineage)")
    q.add_argument("name")
    g = q.add_mutually_exclusive_group()
    g.add_argument("--resolved", action="store_true", help="the full config it resolves to")
    g.add_argument("--lineage", action="store_true", help="the chain of parents back to the root")
    q.set_defaults(fn=cmd_presets_show)
    q = ps.add_parser("save", help="save a design as a preset that lists only what differs from its parent")
    q.add_argument("name", help="plain name for the new preset, e.g. rose_room")
    q.add_argument("--from", dest="parent", default="poolrooms", help="parent preset (default: poolrooms)")
    q.add_argument("--config", help="a config.json written by make/variants to keep as a preset")
    q.add_argument("--set", action="append", metavar="KEY=VALUE", help="change a value on top of the parent")
    q.add_argument("--description", help="one line on what makes this design")
    q.add_argument("--tags", help="comma-separated, e.g. pink,dusk")
    q.add_argument("--dir", help="folder to save into (default: first WAVEGEN_PRESET_PATH folder, else bundled)")
    q.add_argument("--force", action="store_true", help="replace an existing preset, or shadow a bundled one")
    q.set_defaults(fn=cmd_presets_save)
    q = ps.add_parser("catalog", help="write PRESETS.md with a rendered thumbnail per preset")
    q.add_argument("--out", default="docs", help="folder for PRESETS.md and presets/ thumbnails (default: docs)")
    q.add_argument("--no-render", action="store_true", help="rewrite the page only, keep existing thumbnails")
    q.set_defaults(fn=cmd_presets_catalog)

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
