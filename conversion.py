import re
from typing import Dict, List

from aqt import mw
from aqt.utils import tooltip

from .hepburn import to_hepburn

POS_VERB_KEYS = ("godan", "ichidan", "suru")
POS_ADJ_KEYS = ("na/i",)

DEFAULT_FIELD_MAPPING = {
    "Vocab": "computed:Vocab",
    "VocabReading": "value:VocabReading",
    "VocabMeaning": "computed:VocabMeaning",
    "VocabHepburn": "computed:VocabHepburn",
    "VocabAudio": "value:VocabAudio",
    "FamilyID": "computed:FamilyID",
}

VALUE_SOURCES = [
    ("ignore", "(Ignorieren)"),
    ("value:Vocab", "Vocab (Quellfeld)"),
    ("value:VocabReading", "VocabReading (Quellfeld)"),
    ("value:VocabFurigana", "VocabFurigana (Quellfeld)"),
    ("value:VocabAudio", "VocabAudio (Quellfeld)"),
    ("value:POS", "POS (Quellfeld)"),
    ("value:GlossaryJMDictGerHTML", "GlossaryJMDictGerHTML (Quellfeld)"),
    ("value:GlossaryJitendexEndHTML", "GlossaryJitendexEndHTML (Quellfeld)"),
    ("value:GlossaryFirst", "GlossaryFirst (Quellfeld)"),
    ("value:SelectionText", "SelectionText (Quellfeld)"),
    ("value:Tags", "Tags (Quellfeld)"),
    ("value:FreqJPDB", "FreqJPDB (Quellfeld)"),
    ("value:FeqJPDB", "FeqJPDB (Quellfeld)"),
    ("value:FreqJLPT", "FreqJLPT (Quellfeld)"),
    ("computed:Vocab", "Vocab = VocabFurigana"),
    ("computed:VocabMeaning", "VocabMeaning = SelectionText -> GlossaryFirst"),
    ("computed:VocabHepburn", "VocabHepburn aus VocabReading"),
    ("computed:FamilyID", "FamilyID = VocabFurigana"),
]


def detect_pos_category(pos_value: str) -> str:
    pos = (pos_value or "").lower()
    if any(k in pos for k in POS_ADJ_KEYS):
        return "adjective"
    if any(k in pos for k in POS_VERB_KEYS):
        return "verb"
    return "other"


def _normalize_tags(raw: str) -> List[str]:
    if not raw:
        return []
    parts = re.split(r"[\s,;]+", raw)
    return [p for p in parts if p]


def _safe_tag_component(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[\[\]<>]", "", text)
    return text


def _get_field(note, name: str) -> str:
    return note[name] if name in note else ""


def _compute_value(key: str, source_note) -> str:
    if not key or key == "ignore":
        return ""
    if key.startswith("value:"):
        field = key.split(":", 1)[1]
        return _get_field(source_note, field)
    if key == "computed:Vocab":
        return _get_field(source_note, "VocabFurigana")
    if key == "computed:VocabMeaning":
        val = _get_field(source_note, "SelectionText")
        if not val:
            val = _get_field(source_note, "GlossaryFirst")
        return val
    if key == "computed:VocabHepburn":
        return to_hepburn(_get_field(source_note, "VocabReading"))
    if key == "computed:FamilyID":
        return _get_field(source_note, "VocabFurigana")
    return ""


def _collect_tags(source_note, cfg: Dict) -> List[str]:
    tags = set()
    tags_field = _get_field(source_note, "Tags")
    for t in _normalize_tags(tags_field):
        tags.add(t)

    freq_jpdb = _get_field(source_note, "FreqJPDB") or _get_field(source_note, "FeqJPDB")
    if freq_jpdb:
        m = re.search(r"\d+", freq_jpdb)
        if m:
            tags.add(f"Freq::{m.group(0)}")

    jlpt = _get_field(source_note, "FreqJLPT")
    if jlpt:
        m = re.search(r"([1-5])", jlpt)
        if m:
            tags.add(f"JLPT::N{m.group(1)}")

    tags.add(cfg["tags"]["export_tag"])

    vocab = _get_field(source_note, "VocabFurigana") or _get_field(source_note, "Vocab")
    vocab_safe = _safe_tag_component(vocab)
    if vocab_safe:
        link_tag = f"{cfg['tags']['link_tag_prefix']}::{vocab_safe}::{source_note.id}"
        tags.add(link_tag)

    return sorted(tags)


def _mark_source_note(source_note, cfg: Dict):
    processed_tag = cfg["tags"]["processed_tag"]
    vocab = _get_field(source_note, "VocabFurigana") or _get_field(source_note, "Vocab")
    vocab_safe = _safe_tag_component(vocab)
    link_tag = None
    if vocab_safe:
        link_tag = f"{cfg['tags']['link_tag_prefix']}::{vocab_safe}::{source_note.id}"

    if processed_tag not in source_note.tags:
        source_note.tags.append(processed_tag)
    if link_tag and link_tag not in source_note.tags:
        source_note.tags.append(link_tag)
    source_note.flush()


def _get_target_model(col, model_id: int):
    if not model_id:
        return None
    try:
        return col.models.get(model_id)
    except Exception:
        return None


def _apply_field_mapping(target_note, source_note, field_map: Dict, target_model: Dict):
    for fld in target_model["flds"]:
        name = fld["name"]
        key = field_map.get(name, "ignore")
        if key == "ignore":
            continue
        target_note[name] = _compute_value(key, source_note)


def _ensure_defaults(field_map: Dict, target_model) -> Dict:
    out = dict(field_map or {})
    for fld in target_model["flds"]:
        name = fld["name"]
        if name not in out and name in DEFAULT_FIELD_MAPPING:
            out[name] = DEFAULT_FIELD_MAPPING[name]
    return out


def convert_notes(cfg: Dict, manual: bool = False):
    col = mw.col
    if not col:
        return

    source_ids = cfg.get("source_note_type_ids") or []
    if not source_ids:
        if manual:
            tooltip("Keine Quell-Notetypen ausgewaehlt.")
        return

    pos_map = cfg.get("pos_mappings") or {}
    total_created = 0
    total_skipped = 0

    mw.progress.start(immediate=True)
    try:
        for source_model_id in source_ids:
            source_model = _get_target_model(col, source_model_id)
            if not source_model:
                continue

            processed_tag = cfg["tags"]["processed_tag"]
            model_name = source_model["name"]
            query = f'note:"{model_name}" -tag:"{processed_tag}"'
            note_ids = col.find_notes(query)
            for nid in note_ids:
                source_note = col.get_note(nid)
                pos_value = _get_field(source_note, "POS")
                category = detect_pos_category(pos_value)
                mapping = pos_map.get(category) or {}
                target_model_id = mapping.get("note_type_id")
                target_model = _get_target_model(col, target_model_id)
                if not target_model:
                    total_skipped += 1
                    continue

                field_map = _ensure_defaults(mapping.get("field_map") or {}, target_model)
                new_note = col.new_note(target_model)
                _apply_field_mapping(new_note, source_note, field_map, target_model)
                new_note.tags = _collect_tags(source_note, cfg)

                deck_id = col.decks.current()["id"]
                try:
                    col.add_note(new_note, deck_id)
                except TypeError:
                    col.addNote(new_note)

                _mark_source_note(source_note, cfg)
                total_created += 1
    finally:
        mw.progress.finish()

    if manual:
        tooltip(f"Yomitan-Import: {total_created} erstellt, {total_skipped} uebersprungen.")
