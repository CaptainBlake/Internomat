from pathlib import Path
import sys


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_data_root() -> Path:
    """Return writable application root.

    In source runs this is the repository root.
    In frozen runs this is the executable directory.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent

    # src/core/pathing.py -> ../.. = repository root
    return Path(__file__).resolve().parents[2]


def bundle_root() -> Path:
    """Return bundled resource root used by PyInstaller (_MEIPASS)."""
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    return app_data_root()


def data_path(*parts: str) -> Path:
    return app_data_root().joinpath(*parts)


def resource_path(*parts: str) -> Path:
    return bundle_root().joinpath(*parts)
