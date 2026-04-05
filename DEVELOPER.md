# Developer Stuff


## Architecture
- python: 3.14.2
- GUI: PySide6
- Local database: SQLite (`internomat.db`)
- External API: Leetify
- Fallback: Selenium-based scraper
- Internal-Match-Scrapper: MySQL (MatchZy sync)
- use/update `requirements.txt` for import-handling

---

## Setup

Recommended:

```txt
Python 3.12.10
```

Create and activate a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` file:

```env
LEETIFY_API=your_api_key

MATCHZY_DB_HOST=...
MATCHZY_DB_USER=...
MATCHZY_DB_PASSWORD=...
MATCHZY_DB_NAME=...
```

---

## Run from source

Start the application with:

```bash
python src/main.py
```

Entry point: `main.py`

---

## Debugging (VSCode)

Example `launch.json`:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Internomat (venv)",
            "type": "debugpy",
            "request": "launch",
            "program": "${workspaceFolder}/src/main.py",
            "cwd": "${workspaceFolder}",
            "console": "integratedTerminal",
            "envFile": "${workspaceFolder}/.env",
            "justMyCode": true,
            "python": "${workspaceFolder}\\.venv\\Scripts\\python.exe"
        }
    ]
}
```

Notes:

- Ensure VSCode uses the `.venv` interpreter  
- The `.env` file is automatically loaded  

---
## How the application works

### High-level flow

1. Application starts  
2. Local initialization runs  
3. GUI is launched  
4. User inputs data (players, maps)  
5. Core logic processes input:
   - player data retrieval
   - team balancing
   - map selection  
6. Results are displayed in the UI  

---

### Player flow

- User inputs a Steam profile link  
- The app resolves the Steam ID  
- Player data is fetched from the Leetify API  
- If unavailable, a Selenium-based fallback scraper is used  
- Data is passed to the UI  

---

### Team generation

- Players are selected into a pool  
- All possible unique team combinations are generated  
- For each combination:
  - total rating difference is calculated  
  - distribution difference between players is calculated  
- A combined score is computed:

```
score = total_diff + (distribution_diff * weight)
```

- The best (lowest) score is determined  
- All combinations within a configurable tolerance of the best score are considered valid  
- One valid combination is selected randomly  

This approach avoids deterministic results while still ensuring strong balance quality.

---

### Map roulette

- Maps are loaded from the local pool  
- A winning map is selected instantly using uniform randomness  

```txt
winner = core.choose_random_map(maps)
```

- The UI simulates a slot-machine-style animation:
  - a randomized sequence of maps is generated  
  - the winner is injected at the end of the sequence  
  - the animation scrolls through maps with decreasing speed (ease-out)  

- The animation always lands on the preselected winner  

- After the spin:
  - the winning map is highlighted  
  - a pulse animation is applied  
  - a fireworks effect is triggered  

This separates logic (true randomness) from presentation (animated reveal).

---

## Build process

The project uses PyInstaller for app bundling and Inno Setup for installer creation.

### 1) Build app bundle (default: one-folder)

```bash
python src/build.py
```

Output:

```txt
dist/Internomat/
  Internomat.exe
  ...runtime files...
```

### 2) Optional: sign executable

```bash
python src/build.py --sign
```

Requirements:

- `CERT_PASSWORD` in `.env`
- certificate at `internomat.pfx`
- Windows SDK (`signtool.exe`)

### 3) Build installer wizard (install dir + desktop shortcut task)

```bash
python src/build.py --installer --version 0.1.0
```

If Inno Setup is not installed yet:

```bash
python src/build.py --installer --ensure-iscc --version 0.1.0
```

Requirements:

- Inno Setup 6 (`ISCC.exe`) installed
- `ISCC.exe` can be found via `INNO_SETUP_COMPILER`, system `PATH`, or common install locations
- installer definition: `installer/Internomat.iss`

Installer output:

```txt
dist/Internomat-Setup-<version>.exe
```

### Optional one-file build (debug/legacy)

```bash
python src/build.py --onefile
```

---

## Notes

- The build must be executed inside the virtual environment  
- The `.env` file is **not** bundled into build artifacts  
- Runtime secrets should be provided via OS environment variables or a local `.env` on the target machine  

---

## Dependencies

See `requirements.txt`

---

## License

GNU General Public License v3.0