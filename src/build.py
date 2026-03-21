import subprocess
import sys

cmd = [
    sys.executable, "-m", "PyInstaller",
    "src/main.py",
    "--onefile",
    "--windowed",
    "--name", "Internomat",
    "--icon=assets/duck_icon.ico",
    "--collect-all", "selenium",
    "--collect-all", "mysql.connector",
    "--add-data", ".env;.",
    "--add-data", "assets;assets",
    "--add-data", "styles/app.qss;styles",
    "--clean"
]

print("Running build with:", sys.executable)
subprocess.run(cmd, check=True)