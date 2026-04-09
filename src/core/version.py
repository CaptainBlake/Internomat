import json
from dataclasses import dataclass
from pathlib import Path

from core.pathing import is_frozen, resource_path


DEV_APP_VERSION = "1.0.0"
GITHUB_OWNER = "CaptainBlake"
GITHUB_REPO = "Internomat"


def _load_bundled_version() -> str | None:
    if not is_frozen():
        return None

    meta_path = resource_path("bootstrap", "build_meta.json")
    if not Path(meta_path).exists():
        return None

    try:
        payload = json.loads(Path(meta_path).read_text(encoding="utf-8"))
        value = str(payload.get("app_version") or "").strip()
        return value or None
    except Exception:
        return None


APP_VERSION = _load_bundled_version() or DEV_APP_VERSION


@dataclass(frozen=True)
class ReleaseConfig:
    owner: str = GITHUB_OWNER
    repo: str = GITHUB_REPO
    installer_prefix: str = "Internomat-Setup-"
    installer_suffix: str = ".exe"


RELEASE_CONFIG = ReleaseConfig()
