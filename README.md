# AJpC Yomitran

Anki Add-on zum Umwandeln von importierten Yomitan-Notizen (JMDict German) in eigene Vokabel-Notetypen.

## Features
- POS-Erkennung (Verb/Adjektiv/Sonstige) und Zuweisung auf Ziel-Notetypen
- Feldmapping pro POS-Kategorie mit Dropdown-Auswahl
- Hepburn-Transliteration aus `VocabReading` (optional via `pykakasi`, sonst Fallback)
- Tags: JMDict-Tags, Frequenz (`Freq::`), JLPT (`JLPT::N*`), interne Tracking-Tags
- Automatisch nach Sync (abschaltbar) + manueller Start im AJpC-Menue

## Installation (lokal)
1) Ordner nach `Anki2/addons21/ajpc-yomitran_dev` kopieren.
2) Anki neu starten.
3) In Anki unter `Tools -> AJpC -> Yomitan-Import Einstellungen` konfigurieren.

## Konfiguration
- `config.json` wird von Anki verwaltet (nicht versioniert)
- Beispiel: `config.example.json`

### Beispiel-Felder (Quelle)
Quellfelder, die erwartet werden:
- Vocab, VocabReading, VocabFurigana, VocabAudio, POS
- GlossaryJMDictGerHTML, GlossaryJitendexEndHTML, GlossaryFirst
- SelectionText, Tags, FreqJPDB/FeqJPDB, FreqJLPT

### Ziel-Felder (berechnet)
- Vocab = VocabFurigana
- VocabReading = VocabReading
- VocabMeaning = SelectionText (Fallback GlossaryFirst)
- VocabHepburn = Hepburn(VocabReading)
- VocabAudio = VocabAudio
- FamilyID = VocabFurigana

## Build (.ankiaddon)
GitHub Actions Workflow erzeugt ein `.ankiaddon`-Artifact.

Lokaler Build (manuell):
```
zip -r ajpc-yomitran_dev.ankiaddon . -x ".git/*" ".github/*" "config.json" "__pycache__/*" "*.pyc" "*.pyo"
```

## Hinweise
- Die Ziel-Noten landen im aktuell aktiven Deck.
- Tags aus dem Feld `Tags` werden als Anki-Tags uebernommen.
- Interne Tags:
  - `_intern::yomitan_export`
  - `_intern::yomitan::processed`
  - `_intern::yomitan::VOCAB_AUS_DEM_ES_STAMMT::<Vocab>::<NoteID>`
