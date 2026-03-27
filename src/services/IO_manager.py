import os
import json

from pathlib import Path


class IOManager:

    # --- json ---

    @staticmethod
    def read_json(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def write_json(filepath, data, indent=2):
        directory = os.path.dirname(filepath)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent)

    @staticmethod
    def read_cfg(filepath):
        payload = {}
        with open(filepath, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("#") or line.startswith(";"):
                    continue
                if "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if not key:
                    continue
                payload[key] = value

        return payload

    @staticmethod
    def write_cfg(filepath, data):
        directory = os.path.dirname(filepath)
        if directory:
            os.makedirs(directory, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# Internomat settings export\n")
            f.write("# Format: key=value\n\n")
            for key in sorted(data.keys()):
                value = data[key]
                if isinstance(value, bool):
                    rendered = "true" if value else "false"
                else:
                    rendered = "" if value is None else str(value)
                f.write(f"{key}={rendered}\n")

    # --- filesystem ---

    @staticmethod
    def ensure_dir(path):
        os.makedirs(path, exist_ok=True)

    @staticmethod
    def file_exists(filepath):
        return os.path.exists(filepath)

    # --- binary / streaming ---

    @staticmethod
    def open_binary_writer(filepath):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        return open(filepath, "wb")

    @staticmethod
    def stream_to_file(filepath, stream_func, total_size=None, desc=None, progress_callback=None):
        """
        stream_func(callback) should call callback(bytes)
        """

        from tqdm import tqdm

        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, "wb") as f, tqdm(
            total=total_size,
            unit="B",
            unit_scale=True,
            desc=desc,
            leave=False,
        ) as pbar:

            bytes_written = 0

            def callback(data):
                nonlocal bytes_written
                f.write(data)
                bytes_written += len(data)
                if total_size:
                    pbar.update(len(data))
                if callable(progress_callback):
                    try:
                        progress_callback(bytes_written, total_size)
                    except Exception:
                        pass

            stream_func(callback)

    @staticmethod
    def list_files(directory, extension=None, recursive=False):
        directory = Path(directory)

        if extension:
            pattern = f"**/*{extension}" if recursive else f"*{extension}"
            return list(directory.glob(pattern))

        return list(directory.rglob("*") if recursive else directory.iterdir())

    @staticmethod
    def list_parsed_demo_sources(parsed_dir):
        """
        Return DEM filenames that already have a parsed payload in parsed_dir.
        Expected parsed payload naming: <demo_stem>.pkl (e.g. file.pkl for file.dem).
        Backward compatible with legacy .dem.pkl and .pkl.gz payloads.
        """

        parsed_path = Path(parsed_dir)
        if not parsed_path.exists():
            return set()

        parsed_sources = set()
        for file in parsed_path.iterdir():
            if not file.is_file():
                continue

            name = file.name
            if name.endswith(".pkl") and not name.endswith(".dem.pkl"):
                parsed_sources.add(f"{name[:-4]}.dem")
                continue

            if name.endswith(".dem.pkl"):
                parsed_sources.add(name[:-4])
                continue

            if name.endswith(".dem.pkl.gz"):
                parsed_sources.add(name[:-7])

        return parsed_sources
    
