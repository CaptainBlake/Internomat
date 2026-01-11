# Internomat

Internomat ist ein einfaches Python-Tool mit grafischer Oberfläche (Tkinter), das Spielerteams anhand von Ratings möglichst ausgeglichen auslost.

---

## Funktionen

- Grafische Benutzeroberfläche mit Tkinter
- Auslosen von zwei Teams
- Berücksichtigung von Spieler-Ratings
- Unterstützung von Rating-Bereichen (z. B. `8000-10000`)
- Konfigurierbare Anzahl an Iterationen
- Konfigurierbare maximale Rating-Differenz
- Option für gleiche Teamgröße
- Speichern und Laden der Spieler über `players.json`

---

## Eingabeformat

Spieler werden zeilenweise im folgenden Format eingegeben:

```
Name,Rating
```

Beispiele:

```
Alice,12000
Bob,15000
Charlie,8000-10000
```

Bei Rating-Bereichen wird beim Losen ein zufälliger Wert innerhalb des Bereichs verwendet und im Ergebnis angezeigt.

---

## Einstellungen

``` Max. Differenz
Legt fest, ab welcher maximalen Rating-Differenz der Algorithmus abbrechen darf, wenn eine passende Aufteilung gefunden wurde.

``` Iterationen
Gibt an, wie oft versucht wird, eine bessere Teamaufteilung zu finden.

``` Gleiche Teamgröße
Wenn aktiviert, werden die Teams gleich groß erstellt (Spieleranzahl muss gerade sein).

---

## Speicherung

- Spieler können über den Button **„Spieler speichern“** gespeichert werden
- Die Daten werden in der Datei `players.json` abgelegt
- Beim Start des Programms werden gespeicherte Spieler automatisch geladen

