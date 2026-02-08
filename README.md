# AJpC Yomitran

Anki add-on for converting imported Yomitan notes into your own vocabulary note types.

Note: This project is not affiliated with or endorsed by Yomitan.

## Requirements
- `Yomitan` (browser extension) for creating/importing source notes in Anki.
- `AnkiConnect` add-on in Anki (default local API at `http://127.0.0.1:8765`).

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
- `config.json` is managed directly by this add-on (not via Anki's add-on meta config).
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

## Notes
- New notes are added to the currently active deck.
- Tags from the source field `Tags` are transformed and applied.
- Internal tags:
  - `_intern::yomitan_export`
  - `_intern::yomitan::processed`
  - `_intern::yomitan::<Vocab>::<NoteID>`

## Hepburn dependency
This add-on bundles `pykakasi` and its dependencies, so no manual installation is required.
The vendored packages live in `vendor/`.

If the vendored copy is missing or broken, conversion will raise an error.

## Licensing
This project is distributed under GPLv3 (see `LICENSE`).
Third-party license texts are included under `third_party/` and summarized in `THIRD_PARTY_NOTICES.md`.
