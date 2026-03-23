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
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent)

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
    def stream_to_file(filepath, stream_func, total_size=None, desc=None):
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

            def callback(data):
                f.write(data)
                if total_size:
                    pbar.update(len(data))

            stream_func(callback)

    @staticmethod
    def list_files(directory, extension=None, recursive=False):
        directory = Path(directory)

        if extension:
            pattern = f"**/*{extension}" if recursive else f"*{extension}"
            return list(directory.glob(pattern))

        return list(directory.rglob("*") if recursive else directory.iterdir())
    
