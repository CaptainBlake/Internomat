import re
import hashlib
from pathlib import Path
from tempfile import gettempdir
from dataclasses import dataclass
from typing import Optional

import requests

from core.version import APP_VERSION, RELEASE_CONFIG


_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


@dataclass(frozen=True)
class UpdateCheckResult:
    current_version: str
    latest_version: str
    update_available: bool
    comparison_basis: str
    release_url: str
    installer_download_url: str
    tag_name: str
    release_name: str
    published_at: str
    release_id: int
    installer_asset_name: str
    checksums_asset_name: str
    checksums_download_url: str


@dataclass(frozen=True)
class DownloadedInstaller:
    file_path: str
    sha256: str
    verified_with_release_checksums: bool


def _parse_version(version_text: str) -> tuple[int, int, int]:
    match = _VERSION_RE.match((version_text or "").strip())
    if not match:
        raise ValueError(f"Unsupported version format: {version_text}")
    return tuple(int(part) for part in match.groups())


def _normalize_version(version_text: str) -> str:
    return version_text.strip().lstrip("v")


def _build_latest_release_api_url() -> str:
    return (
        f"https://api.github.com/repos/{RELEASE_CONFIG.owner}/{RELEASE_CONFIG.repo}/releases/latest"
    )


def _build_release_api_url(release_id: int) -> str:
    return (
        f"https://api.github.com/repos/{RELEASE_CONFIG.owner}/{RELEASE_CONFIG.repo}/releases/{release_id}"
    )


def _best_installer_asset(assets: list[dict]) -> Optional[dict]:
    prefix = RELEASE_CONFIG.installer_prefix
    suffix = RELEASE_CONFIG.installer_suffix
    matches = [
        asset
        for asset in assets
        if str(asset.get("name", "")).startswith(prefix)
        and str(asset.get("name", "")).lower().endswith(suffix)
    ]
    if not matches:
        return None
    matches.sort(key=lambda a: a.get("name", ""))
    return matches[-1]


def _best_checksums_asset(assets: list[dict]) -> Optional[dict]:
    candidates = []
    for asset in assets:
        name = str(asset.get("name", "")).lower()
        if any(token in name for token in ["sha256", "checksums", "checksum"]):
            candidates.append(asset)
    if not candidates:
        return None
    candidates.sort(key=lambda a: a.get("name", ""))
    return candidates[-1]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_checksums_manifest(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        # Accept common formats:
        # 1) "<sha256>  <filename>"
        # 2) "SHA256(<filename>)=<sha256>"
        m1 = re.match(r"^([a-fA-F0-9]{64})\s+\*?(.+)$", line)
        if m1:
            result[m1.group(2).strip()] = m1.group(1).lower()
            continue

        m2 = re.match(r"^sha256\((.+)\)\s*=\s*([a-fA-F0-9]{64})$", line, flags=re.IGNORECASE)
        if m2:
            result[m2.group(1).strip()] = m2.group(2).lower()
            continue

    return result


def check_latest_release(timeout_seconds: float = 8.0) -> UpdateCheckResult:
    """Check for updates using semantic version comparison only.

    Important: setup/app hashes are not used to decide update availability,
    because installer hashes naturally differ from client/runtime file hashes.
    Hashes are only useful for download integrity verification.
    """
    response = requests.get(
        _build_latest_release_api_url(),
        headers={"Accept": "application/vnd.github+json"},
        timeout=timeout_seconds,
    )
    response.raise_for_status()

    payload = response.json()
    tag_name = str(payload.get("tag_name") or "").strip()
    latest_version = _normalize_version(tag_name)

    current_tuple = _parse_version(APP_VERSION)
    latest_tuple = _parse_version(latest_version)
    update_available = latest_tuple > current_tuple

    assets = payload.get("assets") or []
    installer_asset = _best_installer_asset(assets)
    checksums_asset = _best_checksums_asset(assets)
    release_url = (
        str(installer_asset.get("browser_download_url"))
        if installer_asset
        else str(payload.get("html_url") or "")
    )
    installer_download_url = str(installer_asset.get("browser_download_url") or "") if installer_asset else ""

    return UpdateCheckResult(
        current_version=APP_VERSION,
        latest_version=latest_version,
        update_available=update_available,
        comparison_basis="semver",
        release_url=release_url,
        installer_download_url=installer_download_url,
        tag_name=tag_name,
        release_name=str(payload.get("name") or ""),
        published_at=str(payload.get("published_at") or ""),
        release_id=int(payload.get("id") or 0),
        installer_asset_name=str(installer_asset.get("name") or "") if installer_asset else "",
        checksums_asset_name=str(checksums_asset.get("name") or "") if checksums_asset else "",
        checksums_download_url=str(checksums_asset.get("browser_download_url") or "") if checksums_asset else "",
    )


def download_and_verify_installer(
    result: UpdateCheckResult,
    target_dir: Optional[Path] = None,
    timeout_seconds: float = 30.0,
) -> DownloadedInstaller:
    if not result.installer_download_url or not result.installer_asset_name:
        raise RuntimeError("Release does not expose a downloadable installer asset.")

    destination_dir = target_dir or (Path(gettempdir()) / "Internomat" / "updates")
    destination_dir.mkdir(parents=True, exist_ok=True)
    installer_path = destination_dir / result.installer_asset_name

    with requests.get(result.installer_download_url, stream=True, timeout=timeout_seconds) as resp:
        resp.raise_for_status()
        with installer_path.open("wb") as out:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    out.write(chunk)

    actual_sha256 = _sha256_file(installer_path)
    verified = False

    if result.checksums_download_url:
        checksum_resp = requests.get(result.checksums_download_url, timeout=timeout_seconds)
        checksum_resp.raise_for_status()
        parsed = _parse_checksums_manifest(checksum_resp.text)
        expected = parsed.get(result.installer_asset_name)
        if expected is None:
            raise RuntimeError(
                "Checksums asset found but installer filename entry is missing. "
                f"Expected entry for {result.installer_asset_name}."
            )
        if expected.lower() != actual_sha256.lower():
            raise RuntimeError(
                "Installer SHA256 mismatch. "
                f"expected={expected.lower()} actual={actual_sha256.lower()}"
            )
        verified = True

    return DownloadedInstaller(
        file_path=str(installer_path),
        sha256=actual_sha256,
        verified_with_release_checksums=verified,
    )
