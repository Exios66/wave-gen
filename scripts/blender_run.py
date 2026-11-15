"""Run the wavegen CLI inside a desktop Blender install (uses Blender's GPU
setup and bundled Python):

    blender -b -P scripts/blender_run.py -- make --preset poolrooms -o out/poolrooms
    blender -b -P scripts/blender_run.py -- build --blend out/poolrooms.blend

Everything after ``--`` is passed to ``python -m wavegen``.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wavegen.cli import main  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
main(argv)
