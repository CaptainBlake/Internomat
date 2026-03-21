import subprocess
import sys
import os
from dotenv import load_dotenv


# ---------- LOAD ENV ----------
load_dotenv()


# ---------- CONFIG ----------
APP_NAME = "Internomat"
DIST_PATH = "dist"
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


def verify_signature(exe_path: str):
    signtool = find_signtool()

    cmd = [signtool, "verify", "/pa", exe_path]
    result = subprocess.run(cmd, capture_output=True, text=True)

    print("[BUILD] Signature verification:")
    print(result.stdout)

    if result.returncode != 0:
        raise RuntimeError("Signature verification failed")


def build():
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "src/main.py",
        "--onefile",
        "--windowed",
        "--name", APP_NAME,
        "--icon=assets/duck_icon.ico",
        "--collect-all", "selenium",
        "--collect-all", "mysql.connector",
        "--add-data", ".env;.",
        "--add-data", "assets;assets",
        "--add-data", "styles/app.qss;styles",
        "--clean"
    ]

    print("[BUILD] Running build with:", sys.executable)
    subprocess.run(cmd, check=True)

    exe_path = os.path.join(DIST_PATH, f"{APP_NAME}.exe")

    print(f"[BUILD] Built EXE at: {exe_path}")

    sign_executable(exe_path)
    verify_signature(exe_path)

    print("[BUILD] Done. Executable is signed and verified.")


if __name__ == "__main__":
    build()