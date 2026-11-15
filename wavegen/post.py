"""Assemble rendered frames + soundtrack into the final video with an ffmpeg
"vapor grade": pastel colour balance, halation glow, chroma fringe, grain,
vignette, and optionally the 'filmed off a CRT/TV with a phone' look of the
reference clip (scanlines, soft barrel, black top band)."""
from __future__ import annotations

import math
import re
import shutil
import subprocess
import wave
from pathlib import Path

from .frames import frame_files, loop_frame_count, missing_frames


class IncompleteLoopError(RuntimeError):
    """Not every frame of the loop (1..N) is on disk."""


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg not found on PATH (needed for post/analyze)")
    return exe


def wash_ramp(wash: dict, width: int) -> str:
    """ffmpeg expression for the wash level across the frame (1 = full tint, 0 = none), static per frame.

    Falls from 1 at the left edge to 0 at ``extent``. With ``peak`` (a fraction of the width) it
    instead rises from ``edge`` at the left edge to 1 at the peak, then falls to 0 at the extent.
    """
    x1 = max(1, round(width * wash.get("extent", 0.45)))
    xp = round(width * wash.get("peak", 0.0))
    if xp <= 0 or xp >= x1:
        return f"max(0\\,1-X/{x1})"
    e = float(wash.get("edge", 0.0))
    return f"if(lt(X\\,{xp})\\,{e:.4f}+{1 - e:.4f}*X/{xp}\\,max(0\\,1-(X-{xp})/{x1 - xp}))"


def filtergraph(pc: dict, width: int, height: int) -> str:
    chain = []
    if pc["grade"]:
        chain += [
            "eq=saturation=1.06:contrast=1.04:brightness=0.0:gamma=1.0",
            # lift shadows to lavender, keep mids cyan, warm the highlights a touch
            "colorbalance=rs=0.03:gs=-0.01:bs=0.07:rm=-0.01:gm=0.01:bm=0.02:rh=0.03:gh=0.01:bh=-0.01",
        ]
    pre = ",".join(chain) or "null"
    g = f"[0:v]{pre},split[base][glow];"
    if pc["halation"] > 0:
        sigma = max(4, round(height / 60))
        g += (f"[glow]gblur=sigma={sigma},colorlevels=rimin=0.75:gimin=0.75:bimin=0.75[h];"
              f"[base][h]blend=all_mode=screen:all_opacity={pc['halation']}[v1];")
    else:
        g += "[glow]nullsink;[base]null[v1];"
    wash = pc.get("pink_wash") or {}
    if wash.get("strength", 0) > 0:
        # multiply a left-to-right gradient (tint colour -> white) over the frame: tints, never brightens
        k = min(1.0, float(wash["strength"]))
        rgb = [1 - k * (1 - c) for c in wash.get("color", (1.0, 0.8, 0.92))]
        ramp = wash_ramp(wash, width)
        ch = {c: f"255*(1-{1 - v:.4f}*{ramp})" for c, v in zip("rgb", rgb)}
        g += (f"color=white:s={width}x{height},format=gbrp,geq=r='{ch['r']}':g='{ch['g']}':b='{ch['b']}'[wash];"
              f"[v1]format=gbrp[v1g];[v1g][wash]blend=all_mode=multiply:shortest=1[v1w];")
        src = "[v1w]"
    else:
        src = "[v1]"
    tail = []
    if pc["chroma_shift"]:
        s = int(pc["chroma_shift"])
        tail.append(f"chromashift=cbh={s}:crh={-s}")
    if pc["crt_on_tv"]:
        tail += [
            "geq=r='r(X,Y)*(0.93+0.07*sin(Y*1.9))':g='g(X,Y)*(0.93+0.07*sin(Y*1.9))':b='b(X,Y)*(0.93+0.07*sin(Y*1.9))'",
            "lenscorrection=k1=-0.035:k2=-0.01",
            f"crop={width}:{int(height * 0.975)}:0:{int(height * 0.025)}",
            f"pad={width}:{height}:0:{int(height * 0.025)}:black",
        ]
    if pc["grain"]:
        tail.append(f"noise=alls={int(pc['grain'])}:allf=t+u")
    if pc["vignette"]:
        tail.append(f"vignette=angle={pc['vignette']}")
    tail.append("format=yuv420p")
    g += f"{src}{','.join(tail)}[vout]"
    return g


AUDIO_MIX = {"bed": "bed.wav", "full": "mix.wav"}


def _stem_path(stems_dir: str | Path, audio_mix: str) -> Path:
    if audio_mix not in AUDIO_MIX:
        raise ValueError(f"audio_mix must be one of {', '.join(AUDIO_MIX)}, got {audio_mix!r}")
    path = Path(stems_dir) / AUDIO_MIX[audio_mix]
    if not path.exists():
        raise FileNotFoundError(f"{path} not found (run `wavegen audio --stems -o {stems_dir}`)")
    return path


def assemble(frames_dir: str | Path, out: str | Path, cfg: dict, stems_dir: str | Path | None = None,
             audio_mix: str = "bed") -> Path:
    """Grade + encode frames 1..N of the loop (N from the config), refusing gaps.

    With ``stems_dir``, mux ``bed.wav`` (room + crt, the default) or ``mix.wav``
    (``audio_mix="full"``) trimmed to exactly the loop length.
    """
    frames_dir, out = Path(frames_dir), Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    files = frame_files(frames_dir)
    if not files:
        raise FileNotFoundError(f"no frames in {frames_dir}")
    n = loop_frame_count(cfg)
    ext = files[0].suffix                    # ffmpeg reads one exact pattern: every frame must match it
    gone = [i for i in range(1, n + 1) if not (frames_dir / f"frame_{i:05d}{ext}").exists()]
    if gone:
        shown = ", ".join(map(str, gone[:20])) + (" ..." if len(gone) > 20 else "")
        raise IncompleteLoopError(f"{len(gone)} of {n} loop frames missing in {frames_dir}: {shown}")
    pattern = f"frame_%05d{ext}"
    rc, pc = cfg["render"], cfg["post"]
    w = int(rc["resolution"][0] * rc["percentage"] / 100)
    h = int(rc["resolution"][1] * rc["percentage"] / 100)
    wav = _stem_path(stems_dir, audio_mix) if stems_dir else None
    cmd = [_ffmpeg(), "-y", "-v", "error", "-framerate", str(rc["fps"]), "-start_number", "1",
           "-i", str(frames_dir / pattern)]
    if wav:
        cmd += ["-i", str(wav)]
    cmd += ["-filter_complex", filtergraph(pc, w, h), "-map", "[vout]", "-frames:v", str(n)]
    if wav:
        cmd += ["-map", "1:a", "-c:a", "aac", "-b:a", "256k", "-t", f"{n / rc['fps']:.6f}"]
    cmd += ["-c:v", "libx264", "-preset", "slow", "-crf", str(pc["crf"]), "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    return out


def parse_duration(s: str) -> float:
    """``"90s"``, ``"45m"``, ``"1h"``, ``"1h30m"`` or plain seconds -> seconds."""
    s = str(s).strip().lower()
    m = re.fullmatch(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s?)?", s)
    if not s or not m or not any(m.groups()):
        raise ValueError(f"bad duration {s!r} (use e.g. 90s, 45m, 1h, 1h30m)")
    h, mi, se = (float(g) if g else 0.0 for g in m.groups())
    return h * 3600 + mi * 60 + se


def extend(loop_mp4: str | Path, stems_dir: str | Path, duration_s: float, out: str | Path,
           audio_mix: str = "bed") -> Path:
    """Repeat a loop to ``duration_s``. Video is stream-copied (no quality loss); the
    audio is rebuilt by tiling the sample-exact stem and encoding once, so the
    joins have no AAC priming clicks."""
    import tempfile

    import numpy as np

    from .audio import write_wav

    loop_mp4, out = Path(loop_mp4).resolve(), Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    wav = _stem_path(stems_dir, audio_mix)
    with wave.open(str(wav)) as wf:
        sr, ch = wf.getframerate(), wf.getnchannels()
        x = np.frombuffer(wf.readframes(wf.getnframes()), "<i2").reshape(-1, ch).astype(np.float32) / 32767
    loop_s = len(x) / sr
    reps = max(1, math.ceil(duration_s / loop_s - 1e-9))
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        lst = td / "list.txt"
        quoted = loop_mp4.resolve().as_posix().replace("'", "'\\''")   # concat-list escaping
        lst.write_text("".join(f"file '{quoted}'\n" for _ in range(reps)))
        tiled = np.tile(x, (reps, 1))[: int(round(duration_s * sr))]
        long_wav = write_wav(td / "long.wav", tiled, sr)
        subprocess.run([_ffmpeg(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-i", str(long_wav), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "256k", "-t", f"{duration_s:.6f}",
                        "-movflags", "+faststart", str(out)], check=True)
    return out
