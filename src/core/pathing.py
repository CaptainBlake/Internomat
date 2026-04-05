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


def _safe_join(root: Path, *parts: str) -> Path:
    """Join parts to root and guarantee the result stays under root."""
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*parts).resolve(strict=False)

    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(
            f"Path escapes root: root={resolved_root} candidate={candidate}"
        ) from exc

    return candidate


def data_path(*parts: str) -> Path:
    return _safe_join(app_data_root(), *parts)


def resource_path(*parts: str) -> Path:
    return _safe_join(bundle_root(), *parts)
