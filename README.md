# Internomat

Internomat ist ein kleines Desktop-Tool zum schnellen Erstellen möglichst ausgeglichener **CS2-Teams**.

Spieler werden über ihren **Steam-Profil-Link** hinzugefügt. Das Programm ruft automatisch Rating-Daten von **Leetify** ab und erstellt daraus zwei möglichst gleich starke Teams.

Zusätzlich enthält Internomat eine **Map Roulette**, um zufällig eine Map aus einem konfigurierbaren Pool auszuwählen.

Alle Spieler und Maps werden lokal gespeichert und können jederzeit wiederverwendet werden.

**Aktueller Release:**  
https://github.com/CaptainBlake/Internomat/releases

---

# Funktionen

## Team Builder

- Grafische Oberfläche
- Spieler über **Steam-Profil-Link** hinzufügen
- Automatisches Abrufen des **Premier Ratings**
- Lokale Spielerdatenbank
- Auswahl eines **Player Pools**
- Generierung möglichst ausgeglichener Teams
- Aktualisieren von Spielerdaten über Leetify
- Sortierbare Spielerliste

## Map Roulette

- Zufällige Map-Auswahl
- Bearbeitbarer Map Pool
- Persistente Speicherung der Maps

---

# Grundprinzip

## Team Builder

1. Spieler über Steam-Link hinzufügen  
2. Spieler in den **Player Pool** verschieben  
3. **Generate Teams** klicken  

Internomat testet mehrere Teamaufteilungen und wählt die mit der geringsten Rating-Differenz.

---

## Map Roulette

1. Maps im Pool verwalten  
2. **Spin** drücken  
3. Eine zufällige Map wird ausgewählt

---

# Spieler hinzufügen

Einfach einen Steam-Profil-Link einfügen und **Add Player** klicken.

Beispiele:

```
https://steamcommunity.com/profiles/76561198012345678
```

oder

```
https://steamcommunity.com/id/spielername
```

Internomat erkennt automatisch:

- Steam64 IDs
- Vanity URLs

---

# Player Database

Die linke Liste enthält alle gespeicherten Spieler.

Aktionen:

- **Add Player** – Spieler hinzufügen  
- **Remove Player** – Spieler löschen  
- **Update** – Spielerdaten aktualisieren  

Die Liste kann über die Spaltenüberschriften sortiert werden.

---

# Player Pool

Die rechte Liste enthält die Spieler für das aktuelle Match.

Spieler hinzufügen:

- Spieler auswählen und `>` drücken  
- oder **Doppelklick**

Spieler entfernen:

- Spieler auswählen und `<` drücken  
- oder **Doppelklick**

---

# Teams generieren

Nachdem Spieler im Pool sind:

1. **Generate Teams** klicken  
2. Zwei Teams werden mit möglichst ähnlicher Gesamtwertung erstellt  

Das Ergebnis erscheint im unteren Bereich.

Internomat führt mehrere zufällige Teamaufteilungen durch und wählt die mit der kleinsten Differenz.

---

# Spieler aktualisieren

Über **Update** können gespeicherte Spieler aktualisiert werden.

Spieler, die kürzlich aktualisiert wurden, werden automatisch übersprungen.

Die Aktualisierung erfolgt über die **Leetify API**.

Falls ein Spieler dort noch kein Ranking hat, wird automatisch ein **Fallback-Scraper** verwendet.

---

# Leetify Fallback

Falls ein Spieler in der API kein Premier-Ranking besitzt, nutzt Internomat einen Fallback:

- Selenium lädt das Leetify-Profil
- Die Seite wird vollständig gerendert
- Das Premier Rating wird aus dem HTML extrahiert

---

# Map Pool

Die Map Roulette nutzt eine lokale Mapliste.

Standardmäßig werden folgende Maps hinzugefügt:

```
de_mirage
de_inferno
de_nuke
de_ancient
de_anubis
de_dust2
de_overpass
```

Maps können im UI hinzugefügt oder entfernt werden.

---

# Lokale Speicherung

Alle Daten werden lokal gespeichert in:

```
internomat.db
```

Die Datenbank enthält zwei Tabellen:

- **players**
- **maps**

Die Datei wird automatisch erstellt.

---

# Windows-Version

Im Ordner `dist` befindet sich eine ausführbare `.exe`.

Diese wurde mit **PyInstaller** erstellt und kann ohne Python gestartet werden.

Beim Start wird automatisch:

- die Datenbank erstellt
- die GUI gestartet

```
def main():
    init_db()
    start_gui()
```

---

# Ausführen aus dem Source-Code

Abhängigkeiten installieren:

```bash
pip install -r requirements.txt
```

Zusätzlich wird eine `.env` Datei benötigt:

```
LEETIFY_API=dein_api_key
```

---

# Build mit PyInstaller

Internomat kann als standalone `.exe` gebaut werden.

Build Command:

```bash
python -m PyInstaller main.py --onefile --windowed --name Internomat_1.x.x --icon=assets/duck_icon.ico --collect-all selenium --add-data ".env;." --clean
```

Der Build erzeugt:

```
dist/
  Internomat_1.x.x.exe
```
---

# Lizenz

Dieses Projekt ist ein Hobbyprojekt und wird ohne Garantie bereitgestellt.
