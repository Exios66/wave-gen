import os
from pathlib import Path

# Keep rendered emblem caches out of the user's home during tests (shared across the session).
os.environ.setdefault("WAVEGEN_CACHE", str(Path(__file__).resolve().parent.parent / ".pytest_cache" / "wavegen"))
