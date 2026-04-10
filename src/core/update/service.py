import re
import hashlib
from pathlib import Path
from tempfile import gettempdir
from dataclasses import dataclass
from typing import Optional

import requests

from core.version import APP_VERSION, RELEASE_CONFIG


_VERSION_RE = re.compile(
    r"^v?(\d+)\.(\d+)\.(\d+)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


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


def _parse_prerelease_identifiers(prerelease: str) -> tuple[int | str, ...]:
    parts: list[int | str] = []
    for part in prerelease.split("."):
        if part.isdigit():
            parts.append(int(part))
        else:
            parts.append(part)
    return tuple(parts)


def _parse_version(version_text: str) -> tuple[int, int, int, tuple[int | str, ...]]:
    match = _VERSION_RE.match((version_text or "").strip())
    if not match:
        raise ValueError(f"Unsupported version format: {version_text}")
    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3))
    prerelease = (match.group(4) or "").strip()
    prerelease_ids = _parse_prerelease_identifiers(prerelease) if prerelease else ()
    return major, minor, patch, prerelease_ids


def _compare_prerelease(
    left: tuple[int | str, ...],
    right: tuple[int | str, ...],
) -> int:
    # Per semver: a normal release has higher precedence than prerelease.
    if not left and not right:
        return 0
    if not left:
        return 1
    if not right:
        return -1

    for l_id, r_id in zip(left, right):
        l_is_num = isinstance(l_id, int)
        r_is_num = isinstance(r_id, int)

        if l_is_num and r_is_num:
            if l_id != r_id:
                return 1 if l_id > r_id else -1
            continue

        if l_is_num != r_is_num:
            # Numeric identifiers have lower precedence than non-numeric.
            return -1 if l_is_num else 1

        l_text = str(l_id)
        r_text = str(r_id)
        if l_text != r_text:
            return 1 if l_text > r_text else -1

    if len(left) == len(right):
        return 0
    return 1 if len(left) > len(right) else -1


def _compare_versions(left: str, right: str) -> int:
    l_major, l_minor, l_patch, l_pre = _parse_version(left)
    r_major, r_minor, r_patch, r_pre = _parse_version(right)

    l_core = (l_major, l_minor, l_patch)
    r_core = (r_major, r_minor, r_patch)
    if l_core != r_core:
        return 1 if l_core > r_core else -1

    return _compare_prerelease(l_pre, r_pre)


def _normalize_version(version_text: str) -> str:
    return version_text.strip().lstrip("v")


def _is_prerelease(version_text: str) -> bool:
    """Return True if the version string contains prerelease identifiers."""
    try:
        _major, _minor, _patch, pre_ids = _parse_version(version_text)
        return len(pre_ids) > 0
    except ValueError:
        return False


def _build_latest_release_api_url() -> str:
    return (
        f"https://api.github.com/repos/{RELEASE_CONFIG.owner}/{RELEASE_CONFIG.repo}/releases/latest"
    )


def _build_releases_list_api_url() -> str:
    return (
        f"https://api.github.com/repos/{RELEASE_CONFIG.owner}/{RELEASE_CONFIG.repo}/releases"
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


def _no_update_result(basis: str = "semver-no-latest-stable") -> UpdateCheckResult:
    return UpdateCheckResult(
        current_version=APP_VERSION,
        latest_version=APP_VERSION,
        update_available=False,
        comparison_basis=basis,
        release_url="",
        installer_download_url="",
        tag_name="",
        release_name="",
        published_at="",
        release_id=0,
        installer_asset_name="",
        checksums_asset_name="",
        checksums_download_url="",
    )


def _result_from_release_payload(payload: dict) -> UpdateCheckResult:
    """Build an UpdateCheckResult from a single GitHub release JSON object."""
    tag_name = str(payload.get("tag_name") or "").strip()
    latest_version = _normalize_version(tag_name)
    update_available = _compare_versions(latest_version, APP_VERSION) > 0

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


def _fetch_latest_unstable_release(timeout_seconds: float) -> UpdateCheckResult:
    """Query /releases and return the highest-versioned release (incl. pre-releases)."""
    response = requests.get(
        _build_releases_list_api_url(),
        headers={"Accept": "application/vnd.github+json"},
        params={"per_page": 25},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    releases = response.json()

    best_payload: Optional[dict] = None
    best_version: Optional[str] = None

    for release in releases:
        if release.get("draft"):
            continue
        tag = str(release.get("tag_name") or "").strip()
        try:
            version = _normalize_version(tag)
            _parse_version(version)
        except ValueError:
            continue

        if best_version is None or _compare_versions(version, best_version) > 0:
            best_version = version
            best_payload = release

    if best_payload is None:
        return _no_update_result("semver-no-releases")

    return _result_from_release_payload(best_payload)


def check_latest_release(
    timeout_seconds: float = 8.0,
    include_unstable: bool = True,
) -> UpdateCheckResult:
    """Check for updates using semantic version comparison only.

    When *include_unstable* is ``True`` (default for backward compatibility),
    pre-release versions (e.g. ``v1.1.0-rc.1``) are considered as update
    candidates.  When ``False``, only stable releases whose version tag
    contains no pre-release identifiers are offered.

    Important: setup/app hashes are not used to decide update availability,
    because installer hashes naturally differ from client/runtime file hashes.
    Hashes are only useful for download integrity verification.
    """
    if include_unstable:
        return _fetch_latest_unstable_release(timeout_seconds)

    # Stable-only path: query /releases/latest (GitHub already excludes
    # GitHub-flagged pre-releases), then additionally verify the tag itself
    # carries no semver pre-release identifiers.
    response = requests.get(
        _build_latest_release_api_url(),
        headers={"Accept": "application/vnd.github+json"},
        timeout=timeout_seconds,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError:
        if response.status_code == 404:
            return _no_update_result()
        raise

    payload = response.json()
    tag_name = str(payload.get("tag_name") or "").strip()
    if _is_prerelease(_normalize_version(tag_name)):
        return _no_update_result("semver-latest-is-prerelease")

    return _result_from_release_payload(payload)


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
