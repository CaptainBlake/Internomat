# Internomat

Internomat is a desktop tool for creating balanced CS2 teams.

Players are added via their Steam profile link. The application automatically retrieves their Leetify rating and generates two teams with similar overall strength.

It also includes a Map Roulette, Leaderboard and Statistics from private game servers (work in progress)

---

## Download

Latest release:  
https://github.com/CaptainBlake/Internomat/releases

---

## Quick Start

1. Download the installer from the Releases page  
2. Run the setup wizard and choose your installation directory  
3. Optionally enable desktop shortcut creation during setup  
4. Start the application  
5. Add players via Steam links  
6. Have fun

---

## Shipping (Maintainers)

Create shipping artifacts locally:

```bash
python src/build.py --installer --version 0.1.0
```

This produces:

- `dist/Internomat/` (one-folder app bundle)
- `dist/Internomat-Setup-0.1.0.exe` (installer wizard)

Installer config lives in `installer/Internomat.iss`.

For signing support and advanced packaging options, see `DEVELOPER.md`.

---

## Development

See `DEVELOPER.md` for setup, build instructions, and technical details.

---

## License

GNU General Public License v3.0  
https://www.gnu.org/licenses/gpl-3.0.html