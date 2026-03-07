# Internomat

Internomat ist ein kleines Desktop-Tool zum schnellen Erstellen möglichst ausgeglichener CS2-Teams.

Spieler werden über ihren **Steam-Profil-Link** hinzugefügt. Das Programm ruft automatisch Rating-Daten von **Leetify** ab und erstellt daraus zwei möglichst gleich starke Teams.

Spieler werden lokal gespeichert und können jederzeit wiederverwendet werden.

---

# Funktionen

- Grafische Oberfläche
- Spieler über **Steam-Profil-Link** hinzufügen
- Automatisches Abrufen des **Premier Ratings**
- Lokale Spielerdatenbank
- Auswahl eines **Player Pools**
- Generierung ausgeglichener Teams
- Aktualisieren von Spielerdaten über Leetify
- Sortierbare Spielerliste

---

# Grundprinzip

1. Spieler über Steam-Link hinzufügen  
2. Spieler in den **Player Pool** verschieben  
3. **Generate Teams** klicken  

Internomat testet mehrere Teamaufteilungen und wählt die mit der geringsten Rating-Differenz.

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

---

# Spieler aktualisieren

Über **Update** können gespeicherte Spieler aktualisiert werden.

Spieler, die kürzlich aktualisiert wurden, werden automatisch übersprungen.

---

# Lokale Speicherung

Spieler werden lokal gespeichert in:

```
players.db
```

Die Datei wird automatisch erstellt.

---

# Windows-Version

Im Ordner `dist` befindet sich eine ausführbare `.exe`.

Diese wurde mit **PyInstaller** erstellt und kann ohne Python gestartet werden.

---

# Ausführen aus dem Source-Code

Abhängigkeiten installieren:

```
pip install -r requirements.txt
playwright install
```

Zusätzlich wird eine `.env` Datei benötigt:

```
LEETIFY_API=dein_api_key
```

---

# Projektstruktur

```
main.py
gui.py
core.py
db.py
```

- **main.py** – Einstiegspunkt  
- **gui.py** – Benutzeroberfläche  
- **core.py** – API & Team-Balancing  
- **db.py** – Datenbank