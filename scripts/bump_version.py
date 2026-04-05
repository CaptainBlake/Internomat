import argparse
import re
from pathlib import Path


_VERSION_RE = re.compile(r'^APP_VERSION\s*=\s*"(\d+)\.(\d+)\.(\d+)"\s*$')
_VERSION_FILE = Path("src") / "core" / "version.py"


def read_version() -> tuple[int, int, int]:
    for line in _VERSION_FILE.read_text(encoding="utf-8").splitlines():
        m = _VERSION_RE.match(line.strip())
        if m:
            return tuple(int(x) for x in m.groups())
    raise RuntimeError("APP_VERSION not found in src/core/version.py")


def write_version(new_version: tuple[int, int, int]) -> None:
    major, minor, patch = new_version
    new_text = _VERSION_FILE.read_text(encoding="utf-8")
    replaced = False
    output_lines = []
    for line in new_text.splitlines():
        if _VERSION_RE.match(line.strip()):
            output_lines.append(f'APP_VERSION = "{major}.{minor}.{patch}"')
            replaced = True
        else:
            output_lines.append(line)
    if not replaced:
        raise RuntimeError("APP_VERSION line could not be replaced")
    _VERSION_FILE.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


def bump(version: tuple[int, int, int], part: str) -> tuple[int, int, int]:
    major, minor, patch = version
    if part == "major":
        return major + 1, 0, 0
    if part == "minor":
        return major, minor + 1, 0
    if part == "patch":
        return major, minor, patch + 1
    raise ValueError(f"Unsupported bump part: {part}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bump APP_VERSION in src/core/version.py")
    parser.add_argument("part", choices=["major", "minor", "patch"], help="Version part to increment")
    args = parser.parse_args()

    current = read_version()
    new_version = bump(current, args.part)
    write_version(new_version)
    print(f"{current[0]}.{current[1]}.{current[2]} -> {new_version[0]}.{new_version[1]}.{new_version[2]}")


if __name__ == "__main__":
    main()
