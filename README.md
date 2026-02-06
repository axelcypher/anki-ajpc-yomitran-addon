# AJpC Yomitran

Anki add-on for converting imported Yomitan notes into your own vocabulary note types.

## Features
- User-defined categories with filters to select the target note type
- Per-category field mapping with dynamic source/virtual fields
- Virtual fields (computed values) with multiple strategies
- Hepburn conversion via `pykakasi`
- Tag transform pipeline (mapping + drop list)
- Auto-run after sync (optional) and manual run from the AJpC menu

## Installation
1) Download the latest `.ankiaddon` file from the repository releases/builds.
2) In Anki, open the Add-ons dialog and choose "Install from file".
3) Select the downloaded `.ankiaddon` and restart Anki.
4) Configure it via `Tools -> AJpC -> Yomitran Settings`.

## Configuration
- `config.json` is managed by Anki.
- `config.example.json` shows the default schema.

### Setup tab
Configure which source fields appear in the mapping dropdown and how they are labeled.
You can also define virtual fields (computed values):
- `copy`: copy a source field
- `fallback`: use a primary field, fallback to another if empty
- `to_hepburn`: convert a source field to Hepburn
- `to_tag`: add the value as tags (not selectable in field mapping)
- `note_link`: create a `[Label|nid123]` link to the source note

### Categories
Each category defines:
- Name
- Target note type
- Filter (source field + values + match mode)
- Field mapping for the target note type

Categories are evaluated in order; the first matching category wins.

### Tag transform
The Tag Transform tab holds a JSON object with `mapping` and `drop` lists.
Example:
```
{
  "mapping": {
    "v5m": "JMDict::v5m",
    "vi": "JMDict::vi",
    "vt": "JMDict::vt"
  },
  "drop": ["spec1", "spec2", "news1", "news2"]
}
```

### Debug logging
Enable debug logging in the settings dialog to write `ajpc-yomitran.log` into the add-on folder.

## Source fields (typical)
Examples of fields you might expose in the Setup tab:
- Vocab, VocabReading, VocabFurigana, VocabAudio, POS
- GlossaryJMDictGerHTML, GlossaryJitendexEndHTML, GlossaryFirst
- SelectionText, Tags, FreqJPDB/FeqJPDB, FreqJLPT

## Virtual field defaults
The default configuration ships with:
- `VocabMeaning`: SelectionText -> GlossaryFirst
- `VocabHepburn`: Hepburn(VocabReading)
- `FamilyID`: copy of VocabFurigana
- `SourceNoteLink`: link to the source note
- `Vocab`: copy of VocabFurigana

## Hepburn dependency
This add-on bundles `pykakasi` and its dependencies, so no manual installation is required.
The vendored packages live in `vendor/`.

If the vendored copy is missing or broken, conversion will raise an error.

## Build (.ankiaddon)
GitHub Actions builds a `.ankiaddon` artifact.

Manual build:
```
zip -r ajpc-yomitran_dev.ankiaddon . -x ".git/*" ".github/*" "config.json" "__pycache__/*" "*.pyc" "*.pyo"
```

## Notes
- New notes are added to the currently active deck.
- Tags from the source field `Tags` are transformed and applied.
- Internal tags:
  - `_intern::yomitan_export`
  - `_intern::yomitan::processed`
  - `_intern::yomitan::<Vocab>::<NoteID>`

## Licensing
This project is distributed under GPLv3 (see `LICENSE`).
Third-party license texts are included under `third_party/` and summarized in `THIRD_PARTY_NOTICES.md`.
