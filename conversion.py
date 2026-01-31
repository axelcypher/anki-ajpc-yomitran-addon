import re
from typing import Dict, List, Optional, Tuple

from aqt import mw
from aqt.utils import tooltip

from .hepburn import to_hepburn
from .logging_utils import get_logger

_LOGGER = get_logger()

DEFAULT_FIELD_MAPPING = {
    "Vocab": "value:Vocab",
    "VocabReading": "value:VocabReading",
    "VocabMeaning": "computed:VocabMeaning",
    "VocabHepburn": "computed:VocabHepburn",
    "VocabAudio": "value:VocabAudio",
    "FamilyID": "computed:FamilyID",
    "LinkedCards": "computed:SourceNoteLink",
}

def _get_source_fields(cfg: Dict) -> List[Dict]:
    raw = cfg.get("source_fields") or []
    out: List[Dict] = []
    if isinstance(raw, dict):
        for name, meta in raw.items():
            if isinstance(meta, dict):
                out.append(
                    {
                        "name": str(name),
                        "label": str(meta.get("label") or name),
                        "enabled": bool(meta.get("enabled", True)),
                    }
                )
    elif isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            out.append(
                {
                    "name": name,
                    "label": str(item.get("label") or name),
                    "enabled": bool(item.get("enabled", True)),
                }
            )
    return out


def _get_virtual_fields(cfg: Dict) -> List[Dict]:
    raw = cfg.get("virtual_fields") or []
    out: List[Dict] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        vid = str(item.get("id") or "").strip()
        if not vid:
            continue
        vtype = str(item.get("type") or "").strip()
        if not vtype:
            continue
        out.append(item)
    return out


def _virtual_field_map(cfg: Dict) -> Dict[str, Dict]:
    return {str(v.get("id")): v for v in _get_virtual_fields(cfg)}


def build_value_sources(cfg: Dict) -> List[Tuple[str, str]]:
    sources: List[Tuple[str, str]] = [("ignore", "(Ignore)")]
    for field in _get_source_fields(cfg):
        if not field.get("enabled", True):
            continue
        name = field.get("name")
        if not name:
            continue
        label = str(field.get("label") or name)
        sources.append((f"value:{name}", label))
    for vf in _get_virtual_fields(cfg):
        vtype = str(vf.get("type") or "").strip()
        if vtype == "to_tag":
            continue
        vid = str(vf.get("id"))
        label = str(vf.get("name") or vid)
        sources.append((f"computed:{vid}", label))
    return sources


def _normalize_tags(raw: str) -> List[str]:
    if not raw:
        return []
    parts = re.split(r"[\s,;]+", raw)
    return [p for p in parts if p]


def _strip_noise_symbols(tag: str, drop: List[str]) -> str:
    if not tag:
        return ""
    for sym in drop:
        tag = tag.replace(sym, "")
    return tag.strip()


def _transform_tags(raw_tags: List[str], cfg: Dict, source_note=None) -> List[str]:
    tcfg = cfg.get("tag_transform") or {}
    prefix = _safe_tag_component(str(tcfg.get("prefix") or ""))
    mapping = tcfg.get("mapping") or {}
    drop = tcfg.get("drop") or []
    out = set()
    for tag in raw_tags:
        cleaned = _strip_noise_symbols(tag, drop)
        if not cleaned or cleaned in drop:
            continue
        if cleaned in mapping:
            mapped = mapping.get(cleaned)
            if isinstance(mapped, list):
                for m in mapped:
                    if m:
                        out.add(m)
            elif mapped:
                out.add(mapped)
            continue
        cleaned_safe = _safe_tag_component(cleaned)
        out.add(f"{prefix}{cleaned_safe}" if prefix else cleaned_safe)
    result = sorted(out)
    _LOGGER.debug("Transformed tags: in=%s out=%s", raw_tags, result)
    return result


def _safe_tag_component(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[\[\]<>]", "", text)
    return text


def _get_field(note, name: str) -> str:
    return note[name] if name in note else ""


def _escape_note_link_label(text: str) -> str:
    if not text:
        return ""
    return text.replace("[", "\\[").replace("]", "\\]")


def _note_label(note) -> str:
    return (
        _get_field(note, "Vocab")
        or _get_field(note, "VocabFurigana")
        or _get_field(note, "SelectionText")
        or (note.fields[0] if getattr(note, "fields", None) else "")
    )


def _compute_virtual_value(vf: Dict, source_note, cfg: Dict) -> str:
    vtype = str(vf.get("type") or "").strip()
    if vtype == "copy":
        return _get_field(source_note, str(vf.get("source") or ""))
    if vtype == "fallback":
        primary = _get_field(source_note, str(vf.get("primary") or ""))
        if primary:
            return primary
        return _get_field(source_note, str(vf.get("fallback") or ""))
    if vtype == "to_hepburn":
        return to_hepburn(_get_field(source_note, str(vf.get("source") or "")))
    if vtype == "note_link":
        label = _escape_note_link_label(str(vf.get("label") or "Source"))
        nid = str(source_note.id)
        return f"[{label}|nid{nid}]" if label else f"[|nid{nid}]"
    if vtype == "to_tag":
        return _get_field(source_note, str(vf.get("source") or ""))
    return ""


def _compute_value(key: str, source_note, cfg: Dict) -> str:
    if not key or key == "ignore":
        return ""
    if key.startswith("value:"):
        field = key.split(":", 1)[1]
        return _get_field(source_note, field)
    if key.startswith("computed:"):
        vid = key.split(":", 1)[1]
        vf = _virtual_field_map(cfg).get(vid)
        if vf:
            return _compute_virtual_value(vf, source_note, cfg)
        # legacy fallbacks
        if vid == "Vocab":
            return _get_field(source_note, "VocabFurigana")
        if vid == "VocabMeaning":
            val = _get_field(source_note, "SelectionText")
            if not val:
                val = _get_field(source_note, "GlossaryFirst")
            return val
        if vid == "VocabHepburn":
            return to_hepburn(_get_field(source_note, "VocabReading"))
        if vid == "FamilyID":
            return _get_field(source_note, "VocabFurigana")
        if vid == "SourceNoteLink":
            label = _escape_note_link_label("Source")
            nid = str(source_note.id)
            return f"[{label}|nid{nid}]" if label else f"[|nid{nid}]"
    return ""


def _collect_tags(source_note, cfg: Dict) -> List[str]:
    tags = set()
    tags_field = _get_field(source_note, "Tags")
    for t in _transform_tags(_normalize_tags(tags_field), cfg, source_note):
        tags.add(t)

    for t in _collect_virtual_tags(source_note, cfg):
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

    vocab = _get_field(source_note, "Vocab") or _get_field(source_note, "VocabFurigana")
    vocab_safe = _safe_tag_component(vocab)
    if vocab_safe:
        link_tag = f"{cfg['tags']['link_tag_prefix']}::{vocab_safe}::{source_note.id}"
        tags.add(link_tag)

    result = sorted(tags)
    _LOGGER.debug("Collected tags for note %s: %s", source_note.id, result)
    return result


def _collect_virtual_tags(source_note, cfg: Dict) -> List[str]:
    tags = set()
    for vf in _get_virtual_fields(cfg):
        vtype = str(vf.get("type") or "").strip()
        if vtype != "to_tag":
            continue
        raw = _compute_virtual_value(vf, source_note, cfg)
        for tag in _normalize_tags(raw):
            tags.add(tag)
    return sorted(tags)


def _mark_source_note(source_note, cfg: Dict, linked_note=None):
    processed_tag = cfg["tags"]["processed_tag"]
    vocab = _get_field(source_note, "Vocab") or _get_field(source_note, "VocabFurigana")
    vocab_safe = _safe_tag_component(vocab)
    link_tag = None
    if vocab_safe:
        link_tag = f"{cfg['tags']['link_tag_prefix']}::{vocab_safe}::{source_note.id}"

    if processed_tag not in source_note.tags:
        source_note.tags.append(processed_tag)
    if link_tag and link_tag not in source_note.tags:
        source_note.tags.append(link_tag)

    if linked_note is not None and "LinkedNotes" in source_note:
        label = _escape_note_link_label("Created Card")
        nid = str(linked_note.id)
        token = f"nid{nid}"
        link = f"[{label}|{token}]" if label else f"[|{token}]"
        current = _get_field(source_note, "LinkedNotes") or ""
        if token not in current:
            sep = "<br>" if current.strip() else ""
            source_note["LinkedNotes"] = f"{current}{sep}{link}"
            _LOGGER.debug(
                "Linked new note %s into source note %s field LinkedNotes",
                nid,
                source_note.id,
            )
    source_note.flush()


def _get_target_model(col, model_id: int):
    if not model_id:
        return None
    try:
        return col.models.get(model_id)
    except Exception:
        return None


def _apply_field_mapping(
    target_note, source_note, field_map: Dict, target_model: Dict, cfg: Dict
):
    for fld in target_model["flds"]:
        name = fld["name"]
        key = field_map.get(name, "ignore")
        if key == "ignore":
            continue
        target_note[name] = _compute_value(key, source_note, cfg)


def _ensure_defaults(field_map: Dict, target_model) -> Dict:
    out = dict(field_map or {})
    for fld in target_model["flds"]:
        name = fld["name"]
        if name not in out and name in DEFAULT_FIELD_MAPPING:
            out[name] = DEFAULT_FIELD_MAPPING[name]
    return out


def _parse_filter_values(raw) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip().lower() for x in raw if str(x).strip()]
    text = str(raw)
    parts = re.split(r"[;,\n]+", text)
    return [p.strip().lower() for p in parts if p.strip()]


def _matches_filter(source_note, filter_cfg: Dict) -> bool:
    if not filter_cfg:
        return True
    field = str(filter_cfg.get("source_field") or "").strip()
    values = _parse_filter_values(filter_cfg.get("values"))
    if not field:
        return True
    if not values:
        return True
    raw = _get_field(source_note, field)
    hay = str(raw or "").lower()
    if not hay:
        return False
    mode = str(filter_cfg.get("mode") or "contains").lower()
    if mode == "equals":
        return any(hay == v for v in values)
    return any(v in hay for v in values)


def _select_category(source_note, categories: List[Dict]) -> Optional[Dict]:
    for cat in categories:
        if not isinstance(cat, dict):
            continue
        filt = cat.get("filter") or {}
        if _matches_filter(source_note, filt):
            return cat
    return None


def convert_notes(cfg: Dict, manual: bool = False):
    col = mw.col
    if not col:
        _LOGGER.warning("Collection not ready; aborting conversion")
        return

    source_id = cfg.get("source_note_type_id")
    if source_id:
        source_ids = [source_id]
    else:
        source_ids = cfg.get("source_note_type_ids") or []
    if not source_ids:
        _LOGGER.info("No source note types configured")
        if manual:
            tooltip("No source note types selected.")
        return

    categories = cfg.get("categories") or []
    if not categories:
        _LOGGER.info("No categories configured")
        if manual:
            tooltip("No categories configured.")
        return
    total_created = 0
    total_skipped = 0

    _LOGGER.info("Starting conversion for source types: %s", source_ids)
    mw.progress.start(immediate=True)
    try:
        for source_model_id in source_ids:
            source_model = _get_target_model(col, source_model_id)
            if not source_model:
                _LOGGER.warning("Source model id not found: %s", source_model_id)
                continue

            processed_tag = cfg["tags"]["processed_tag"]
            model_name = source_model["name"]
            query = f'note:"{model_name}" -tag:"{processed_tag}"'
            note_ids = col.find_notes(query)
            _LOGGER.debug("Found %s source notes for model '%s'", len(note_ids), model_name)
            for nid in note_ids:
                source_note = col.get_note(nid)
                category = _select_category(source_note, categories)
                if not category:
                    _LOGGER.info("Skipping note %s - no category match", nid)
                    total_skipped += 1
                    continue
                target_model_id = category.get("note_type_id")
                target_model = _get_target_model(col, target_model_id)
                if not target_model:
                    _LOGGER.info(
                        "Skipping note %s - no target model for category '%s'",
                        nid,
                        category.get("name") or category.get("id") or "?",
                    )
                    total_skipped += 1
                    continue

                field_map = _ensure_defaults(category.get("field_map") or {}, target_model)
                new_note = col.new_note(target_model)
                _apply_field_mapping(new_note, source_note, field_map, target_model, cfg)
                new_note.tags = _collect_tags(source_note, cfg)

                deck_id = col.decks.current()["id"]
                try:
                    col.add_note(new_note, deck_id)
                except TypeError:
                    col.addNote(new_note)

                _mark_source_note(source_note, cfg, linked_note=new_note)
                total_created += 1
    finally:
        mw.progress.finish()

    _LOGGER.info("Conversion done. created=%s skipped=%s", total_created, total_skipped)
    if manual:
        tooltip(f"Yomitan import: {total_created} created, {total_skipped} skipped.")
