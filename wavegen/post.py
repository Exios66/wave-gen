"""Assemble rendered frames + soundtrack into the final video with an ffmpeg
"vapor grade": pastel colour balance, halation glow, chroma fringe, grain,
vignette, and optionally the 'filmed off a CRT/TV with a phone' look of the
reference clip (scanlines, soft barrel, black top band)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .frames import frame_files, loop_frame_count, missing_frames


class IncompleteLoopError(RuntimeError):
    """Not every frame of the loop (1..N) is on disk."""


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg not found on PATH (needed for post/analyze)")
    return exe


def filtergraph(pc: dict, width: int, height: int) -> str:
    chain = []
    if pc["grade"]:
        chain += [
            "eq=saturation=1.06:contrast=0.97:brightness=0.0:gamma=1.02",
            # lift shadows to lavender, keep mids cyan, warm the highlights a touch
            "colorbalance=rs=0.03:gs=-0.01:bs=0.07:rm=-0.01:gm=0.01:bm=0.02:rh=0.03:gh=0.01:bh=-0.01",
        ]
    pre = ",".join(chain) or "null"
    g = f"[0:v]{pre},split[base][glow];"
    if pc["halation"] > 0:
        sigma = max(4, round(height / 60))
        g += (f"[glow]gblur=sigma={sigma},colorlevels=rimin=0.55:gimin=0.55:bimin=0.55[h];"
              f"[base][h]blend=all_mode=screen:all_opacity={pc['halation']}[v1];")
    else:
        g += "[glow]nullsink;[base]null[v1];"
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
    g += f"[v1]{','.join(tail)}[vout]"
    return g


def assemble(frames_dir: str | Path, out: str | Path, cfg: dict, audio: str | Path | None = None) -> Path:
    """Encode frames 1..N of the loop (N from the config). Refuses gaps."""
    frames_dir, out = Path(frames_dir), Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    files = frame_files(frames_dir)
    if not files:
        raise FileNotFoundError(f"no frames in {frames_dir}")
    n = loop_frame_count(cfg)
    gone = missing_frames(frames_dir, n)
    if gone:
        shown = ", ".join(map(str, gone[:20])) + (" ..." if len(gone) > 20 else "")
        raise IncompleteLoopError(f"{len(gone)} of {n} loop frames missing in {frames_dir}: {shown}")
    pattern = f"frame_%05d{files[0].suffix}"
    rc, pc = cfg["render"], cfg["post"]
    w = int(rc["resolution"][0] * rc["percentage"] / 100)
    h = int(rc["resolution"][1] * rc["percentage"] / 100)
    cmd = [_ffmpeg(), "-y", "-v", "error", "-framerate", str(rc["fps"]), "-start_number", "1",
           "-i", str(frames_dir / pattern)]
    if audio:
        cmd += ["-i", str(audio)]
    cmd += ["-filter_complex", filtergraph(pc, w, h), "-map", "[vout]", "-frames:v", str(n)]
    if audio:
        cmd += ["-map", "1:a", "-c:a", "aac", "-b:a", "256k", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "slow", "-crf", str(pc["crf"]), "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    return out
