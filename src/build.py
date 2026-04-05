import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

APP_NAME = "Internomat"
DIST_PATH = Path("dist")
INSTALLER_SCRIPT = Path("installer") / "Internomat.iss"
BOOTSTRAP_SECRET_PATH = Path("build") / "embedded" / "leetify_bootstrap.bin"
CERT_PATH = r"D:\Git_repo\Internomat\internomat.pfx"
SIGN_PASSWORD = os.getenv("CERT_PASSWORD")  # from .env


def find_signtool():
    base = r"C:\Program Files (x86)\Windows Kits\10\bin"
    candidates = []

    for root, _, files in os.walk(base):
        if "signtool.exe" in files and "x64" in root:
            candidates.append(os.path.join(root, "signtool.exe"))

    if not candidates:
        raise FileNotFoundError("signtool.exe not found. Install Windows SDK.")

    # pick latest version (highest path)
    return sorted(candidates)[-1]


def sign_executable(exe_path: str):
    if not SIGN_PASSWORD:
        raise RuntimeError("CERT_PASSWORD not set in .env")

    signtool = find_signtool()

    if not os.path.exists(exe_path):
        raise FileNotFoundError(f"EXE not found: {exe_path}")

    if not os.path.exists(CERT_PATH):
        raise FileNotFoundError(f"Certificate not found: {CERT_PATH}")

    cmd = [
        signtool,
        "sign",
        "/f", CERT_PATH,
        "/p", SIGN_PASSWORD,
        "/fd", "sha256",
        "/tr", "http://timestamp.digicert.com",
        "/td", "sha256",
        exe_path
    ]

    print("[BUILD] Signing executable...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print("[SIGN ERROR]")
        print(result.stdout)
        print(result.stderr)
        raise RuntimeError("Signing failed")

    print("[BUILD] Signing successful")


def find_iscc():
    env_override = os.getenv("INNO_SETUP_COMPILER")
    if env_override and os.path.exists(env_override):
        return env_override

    from_path = shutil.which("ISCC.exe") or shutil.which("iscc")
    if from_path:
        return from_path

    env_dirs = [
        os.getenv("INNO_SETUP_DIR"),
        os.getenv("INNOSETUPDIR"),
    ]
    for env_dir in env_dirs:
        if env_dir:
            candidate = Path(env_dir) / "ISCC.exe"
            if candidate.exists():
                return str(candidate)

    candidates = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"D:\programs\Inno Setup 6\ISCC.exe",
        r"D:\Program Files\Inno Setup 6\ISCC.exe",
        str(Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe"),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    raise FileNotFoundError(
        "ISCC.exe not found. Install Inno Setup 6 or set INNO_SETUP_COMPILER."
    )


def ensure_iscc_available(auto_install: bool) -> str:
    try:
        return find_iscc()
    except FileNotFoundError:
        if not auto_install:
            raise

    winget = shutil.which("winget")
    if not winget:
        raise FileNotFoundError(
            "ISCC.exe not found and winget is unavailable. Install Inno Setup 6 manually or set INNO_SETUP_COMPILER."
        )

    print("[BUILD] ISCC.exe not found. Installing Inno Setup 6 via winget...")
    install_cmd = [
        winget,
        "install",
        "--id",
        "JRSoftware.InnoSetup",
        "-e",
        "--source",
        "winget",
        "--accept-package-agreements",
        "--accept-source-agreements",
    ]
    subprocess.run(install_cmd, check=True)
    return find_iscc()


def _xor_bytes(payload: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(payload))


def _prepare_bootstrap_secret_bundle() -> bool:
    """Create obfuscated shipping secret bundle from LEETIFY_API when available."""
    api_key = os.getenv("LEETIFY_API", "").strip()
    if not api_key:
        if BOOTSTRAP_SECRET_PATH.exists():
            BOOTSTRAP_SECRET_PATH.unlink()
        print("[BUILD] No LEETIFY_API in environment. Skipping secret bootstrap bundle.")
        return False

    key = os.urandom(32)
    payload = api_key.encode("utf-8")
    cipher = _xor_bytes(payload, key)

    BOOTSTRAP_SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    BOOTSTRAP_SECRET_PATH.write_text(
        json.dumps(
            {
                "v": 1,
                "k": base64.b64encode(key).decode("ascii"),
                "p": base64.b64encode(cipher).decode("ascii"),
            }
        ),
        encoding="utf-8",
    )
    print("[BUILD] Prepared encrypted bootstrap secret bundle for shipping.")
    return True


def _pyinstaller_cmd(onefile: bool):
    # Keep module collection explicit to avoid pulling test/demo payloads from dependencies.
    # This reduces package size while preserving runtime functionality.
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "src/main.py",
        "--windowed",
        "--name", APP_NAME,
        "--icon=assets/duck_icon.ico",
        "--collect-submodules", "selenium",
        "--collect-submodules", "mysql.connector",
        "--collect-all", "seaborn",
        "--collect-all", "matplotlib",
        "--hidden-import", "mysql.connector.plugins.mysql_native_password",
        "--hidden-import", "mysql.connector.plugins.caching_sha2_password",
        "--hidden-import", "matplotlib.figure",
        "--hidden-import", "matplotlib.backends.backend_qtagg",
        "--hidden-import", "matplotlib.backends.qt_compat",
        "--exclude-module", "pytest",
        "--exclude-module", "tkinter",
        "--exclude-module", "IPython",
        "--exclude-module", "jupyter",
        "--exclude-module", "notebook",
        "--exclude-module", "matplotlib.tests",
        "--exclude-module", "numpy.tests",
        "--exclude-module", "pandas.tests",
        "--exclude-module", "scipy.tests",
        "--exclude-module", "PIL.tests",
        "--exclude-module", "pyarrow.tests",
        "--optimize", "1",
        "--add-data", "assets;assets",
        "--add-data", "styles/app.qss;styles",
        "--noconfirm",
        "--clean"
    ]

    if BOOTSTRAP_SECRET_PATH.exists():
        cmd.extend(["--add-data", f"{BOOTSTRAP_SECRET_PATH};bootstrap"])

    if onefile:
        cmd.append("--onefile")
    else:
        # Store PyInstaller runtime dependencies in a dedicated folder.
        cmd.extend(["--contents-directory", "lib"])
    return cmd


def _built_exe_path(onefile: bool) -> Path:
    if onefile:
        return DIST_PATH / f"{APP_NAME}.exe"
    return DIST_PATH / APP_NAME / f"{APP_NAME}.exe"


def build_app(onefile: bool):
    cmd = _pyinstaller_cmd(onefile)
    mode = "onefile" if onefile else "onedir"
    print(f"[BUILD] Running {mode} build with: {sys.executable}")
    subprocess.run(cmd, check=True)

    exe_path = _built_exe_path(onefile)
    print(f"[BUILD] Built executable at: {exe_path}")
    return exe_path


def build_installer(version: str, ensure_iscc: bool = False):
    iscc = ensure_iscc_available(auto_install=ensure_iscc)
    source_dir = (DIST_PATH / APP_NAME).resolve()
    if not source_dir.exists():
        raise FileNotFoundError(
            f"Installer source folder not found: {source_dir}. Run an onedir build first."
        )

    script_path = INSTALLER_SCRIPT.resolve()
    if not script_path.exists():
        raise FileNotFoundError(f"Installer script not found: {script_path}")

    cmd = [
        iscc,
        f"/DMyAppVersion={version}",
        f"/DMyAppSourceDir={source_dir}",
        str(script_path),
    ]

    print("[BUILD] Building installer with Inno Setup...")
    subprocess.run(cmd, check=True)
    print("[BUILD] Installer created in dist/")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build and optionally sign/package Internomat for shipping."
    )
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Build a single-file executable instead of the default one-folder layout.",
    )
    parser.add_argument(
        "--sign",
        action="store_true",
        help="Sign the resulting executable with signtool and the configured certificate.",
    )
    parser.add_argument(
        "--installer",
        action="store_true",
        help="Build a Windows installer (Inno Setup). Requires an onedir build.",
    )
    parser.add_argument(
        "--version",
        default=os.getenv("APP_VERSION", "0.1.0"),
        help="Version string passed to installer metadata (default: APP_VERSION env or 0.1.0).",
    )
    parser.add_argument(
        "--ensure-iscc",
        action="store_true",
        help="If ISCC.exe is missing, install Inno Setup 6 via winget and continue.",
    )
    return parser.parse_args()


def build():
    args = parse_args()
    _prepare_bootstrap_secret_bundle()
    exe_path = build_app(onefile=args.onefile)

    if args.sign:
        sign_executable(str(exe_path))

    if args.installer:
        if args.onefile:
            raise RuntimeError("Installer creation is only supported for onedir builds.")
        build_installer(args.version, ensure_iscc=args.ensure_iscc)

    print("[BUILD] .env is not bundled as a plain file.")
    print("[BUILD] Shipping builds bundle an obfuscated bootstrap secret (if LEETIFY_API is set) and migrate it to Windows encrypted local storage at runtime.")
    print("[BUILD] Done.")


if __name__ == "__main__":
    try:
        build()
    except FileNotFoundError as exc:
        print(f"[BUILD ERROR] {exc}")
        if "ISCC.exe" in str(exc):
            print("[BUILD HINT] Install Inno Setup 6: winget install --id JRSoftware.InnoSetup -e --source winget")
            print("[BUILD HINT] Or run: python src/build.py --installer --ensure-iscc")
        raise SystemExit(1)
    except subprocess.CalledProcessError as exc:
        print(f"[BUILD ERROR] External command failed with exit code {exc.returncode}")
        raise SystemExit(exc.returncode)