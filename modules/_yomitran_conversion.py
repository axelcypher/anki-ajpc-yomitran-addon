import html
import re
from typing import Dict, List, Optional, Tuple

from aqt import mw
from aqt.utils import tooltip

from ._yomitran_hepburn import to_hepburn
from ._yomitran_logging import get_logger

_LOGGER = get_logger()

DEFAULT_FIELD_MAPPING = {
    "Vocab": "value:Vocab",
    "VocabReading": "value:VocabReading",
    "VocabMeaning": "computed:VocabMeaning",
    "VocabHepburn": "computed:VocabHepburn",
    "VocabAudio": "value:VocabAudio",
    "FamilyID": "computed:FamilyID",
    "LinkedCards": "computed:LinkedCards",
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


def _get_value(source_values: Dict[str, str], source_note, name: str) -> str:
    if name in source_values:
        return str(source_values.get(name) or "")
    return _get_field(source_note, name)


def _strip_html_text(value: str) -> str:
    if not value:
        return ""
    txt = str(value)
    txt = re.sub(r"(?is)<\s*br\s*/?\s*>", "\n", txt)
    txt = re.sub(r"(?is)</\s*(li|p|div|tr|ul|ol)\s*>", "\n", txt)
    txt = re.sub(r"(?is)<[^>]+>", "", txt)
    txt = html.unescape(txt)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in txt.splitlines()]
    lines = [ln for ln in lines if ln]
    return " / ".join(lines).strip()


def _normalize_selection_text(value: str) -> str:
    if not value:
        return ""
    txt = str(value)
    txt = re.sub(r"(?is)<\s*br\s*/?\s*>", "\n", txt)
    txt = html.unescape(txt)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in txt.splitlines()]
    lines = [ln for ln in lines if ln]
    return " / ".join(lines).strip()


def _normalize_part_of_speech(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    tokens = [t.strip().lower() for t in re.split(r"[,\n;/|]+", raw) if t.strip()]
    joined = " ".join(tokens)

    has_vs = False
    has_vk = False
    has_vz = False
    has_v1 = False
    has_v5 = False
    has_adj_i = False
    has_adj_na = False
    has_adj_no = False
    has_adj_pn = False
    has_adj_t = False
    has_adj_f = False
    has_n = False

    def _mark_from_token(tok: str) -> None:
        nonlocal has_vs, has_vk, has_vz, has_v1, has_v5
        nonlocal has_adj_i, has_adj_na, has_adj_no, has_adj_pn, has_adj_t, has_adj_f, has_n

        t = tok.strip().lower()
        if not t:
            return

        if t in ("vs", "vs-i", "vs-s", "vs-c") or "suru" in t:
            has_vs = True
        if t == "vk" or "kuru" in t:
            has_vk = True
        if t == "vz" or "zuru" in t:
            has_vz = True
        if t in ("v1", "v1-s") or "ichidan" in t:
            has_v1 = True
        if t.startswith("v5") or "godan" in t:
            has_v5 = True

        if t in ("adj-i", "adj-ix") or "i-adjective" in t:
            has_adj_i = True
        if t == "adj-na" or "na-adjective" in t:
            has_adj_na = True
        if t in ("adj-no", "no-adj"):
            has_adj_no = True
        if t == "adj-pn" or "prenominal" in t:
            has_adj_pn = True
        if t == "adj-t":
            has_adj_t = True
        if t == "adj-f":
            has_adj_f = True

        if t in ("n", "n-adv", "n-t", "n-pref", "n-suf", "n-pr") or t == "noun":
            has_n = True

    for tok in tokens:
        _mark_from_token(tok)
    if not tokens:
        _mark_from_token(joined)

    if has_vs:
        return "suru"
    if has_vk:
        return "kuru"
    if has_vz:
        return "zuru"
    if has_v1:
        return "ichidan"
    if has_v5:
        return "godan"
    if has_adj_i:
        return "i"
    if has_adj_na:
        return "na"
    if has_adj_no:
        return "no"
    if has_adj_pn:
        return "prenominal"
    if has_adj_t:
        return "taru"
    if has_adj_f:
        return "noun-adj"
    if has_n:
        return "noun"
    raw_lower = raw.strip().lower()
    if raw_lower in ("unknown", "none", "n/a", "-"):
        return "unknown"
    if len(tokens) == 1:
        tok = tokens[0]
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]*", tok):
            return tok
    return ""


def _extract_jlpt_level(raw: str) -> str:
    text = _strip_html_text(raw)
    if not text:
        return ""
    m = re.search(r"(?i)\bJLPT\b[^0-9A-Za-z]*N?\s*([1-5])\b", text)
    if m:
        return m.group(1)
    m = re.search(r"(?i)\bN\s*([1-5])\b", text)
    if m:
        return m.group(1)
    return ""


def _build_source_values(source_note, cfg: Dict) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for item in _get_source_fields(cfg):
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        values[name] = _get_field(source_note, name)

    pos_key = "PartOfSpeech"
    raw_pos = values.get(pos_key) or _get_field(source_note, pos_key) or _get_field(source_note, "POS")
    pos = _normalize_part_of_speech(raw_pos)
    if pos:
        values[pos_key] = pos

    sel_key = "SelectionText"
    raw_selection = values.get(sel_key) or _get_field(source_note, sel_key)
    if raw_selection:
        values[sel_key] = _normalize_selection_text(raw_selection)

    raw_first = values.get("GlossaryFirst") or _get_field(source_note, "GlossaryFirst")
    if raw_first:
        values["GlossaryFirst"] = _strip_html_text(raw_first)
    elif not values.get("SelectionText"):
        raw_jmdict = values.get("GlossaryJMDictGerHTML") or _get_field(source_note, "GlossaryJMDictGerHTML")
        if raw_jmdict:
            values["GlossaryFirst"] = _strip_html_text(raw_jmdict)
    return values


def _escape_note_link_label(text: str) -> str:
    if not text:
        return ""
    return text.replace("[", "\\[").replace("]", "\\]")


def _note_label(note, source_values: Dict[str, str] | None = None) -> str:
    sv = source_values or {}
    return (
        _get_value(sv, note, "Vocab")
        or _get_value(sv, note, "VocabFurigana")
        or _get_value(sv, note, "SelectionText")
        or (note.fields[0] if getattr(note, "fields", None) else "")
    )


def _compute_virtual_value(vf: Dict, source_note, cfg: Dict, source_values: Dict[str, str]) -> str:
    vtype = str(vf.get("type") or "").strip()
    if vtype == "copy":
        return _get_value(source_values, source_note, str(vf.get("source") or ""))
    if vtype == "fallback":
        primary = _get_value(source_values, source_note, str(vf.get("primary") or ""))
        if primary:
            return primary
        return _get_value(source_values, source_note, str(vf.get("fallback") or ""))
    if vtype == "to_hepburn":
        return to_hepburn(_get_value(source_values, source_note, str(vf.get("source") or "")))
    if vtype == "note_link":
        label = _escape_note_link_label(str(vf.get("label") or "Source"))
        nid = str(source_note.id)
        return f"[{label}|nid{nid}]" if label else f"[|nid{nid}]"
    if vtype == "to_tag":
        return _get_value(source_values, source_note, str(vf.get("source") or ""))
    return ""


def _compute_value(key: str, source_note, cfg: Dict, source_values: Dict[str, str]) -> str:
    if not key or key == "ignore":
        return ""
    if key.startswith("value:"):
        field = key.split(":", 1)[1]
        return _get_value(source_values, source_note, field)
    if key.startswith("computed:"):
        vid = key.split(":", 1)[1]
        vf = _virtual_field_map(cfg).get(vid)
        if vf:
            return _compute_virtual_value(vf, source_note, cfg, source_values)
        # legacy fallbacks
        if vid == "Vocab":
            return _get_value(source_values, source_note, "VocabFurigana")
        if vid == "VocabMeaning":
            val = _get_value(source_values, source_note, "SelectionText")
            if not val:
                val = _get_value(source_values, source_note, "GlossaryFirst")
            return val
        if vid == "VocabHepburn":
            return to_hepburn(_get_value(source_values, source_note, "VocabReading"))
        if vid == "FamilyID":
            return _get_value(source_values, source_note, "VocabFurigana")
        if vid == "SourceNoteLink":
            label = _escape_note_link_label("Source")
            nid = str(source_note.id)
            return f"[{label}|nid{nid}]" if label else f"[|nid{nid}]"
    return ""


def _collect_tags(source_note, cfg: Dict, source_values: Dict[str, str]) -> List[str]:
    tags = set()
    tags_field = _get_value(source_values, source_note, "Tags")
    for t in _transform_tags(_normalize_tags(tags_field), cfg, source_note):
        tags.add(t)

    for t in _collect_virtual_tags(source_note, cfg, source_values):
        tags.add(t)

    freq_jpdb = _get_value(source_values, source_note, "FreqJPDB") or _get_value(
        source_values, source_note, "FeqJPDB"
    )
    if freq_jpdb:
        m = re.search(r"\d+", freq_jpdb)
        if m:
            tags.add(f"Freq::{m.group(0)}")

    jlpt = _get_value(source_values, source_note, "FreqJLPT")
    if jlpt:
        level = _extract_jlpt_level(jlpt)
        if level:
            tags.add(f"JLPT::N{level}")

    tags.add(cfg["tags"]["export_tag"])

    vocab = _get_value(source_values, source_note, "Vocab") or _get_value(
        source_values, source_note, "VocabFurigana"
    )
    vocab_safe = _safe_tag_component(vocab)
    if vocab_safe:
        link_tag = f"{cfg['tags']['link_tag_prefix']}::{vocab_safe}::{source_note.id}"
        tags.add(link_tag)

    result = sorted(tags)
    _LOGGER.debug("Collected tags for note %s: %s", source_note.id, result)
    return result


def _collect_virtual_tags(source_note, cfg: Dict, source_values: Dict[str, str]) -> List[str]:
    tags = set()
    for vf in _get_virtual_fields(cfg):
        vtype = str(vf.get("type") or "").strip()
        if vtype != "to_tag":
            continue
        raw = _compute_virtual_value(vf, source_note, cfg, source_values)
        for tag in _normalize_tags(raw):
            tags.add(tag)
    return sorted(tags)


def _mark_source_note(source_note, cfg: Dict, source_values: Dict[str, str], linked_note=None):
    processed_tag = cfg["tags"]["processed_tag"]
    vocab = _get_value(source_values, source_note, "Vocab") or _get_value(
        source_values, source_note, "VocabFurigana"
    )
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
        return col.models.get(int(str(model_id)))
    except Exception:
        return None


def _apply_field_mapping(
    target_note, source_note, source_values: Dict[str, str], field_map: Dict, target_model: Dict, cfg: Dict
):
    for fld in target_model["flds"]:
        name = fld["name"]
        key = field_map.get(name, "ignore")
        if key == "ignore":
            continue
        target_note[name] = _compute_value(key, source_note, cfg, source_values)


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


def _matches_filter(source_note, source_values: Dict[str, str], filter_cfg: Dict) -> bool:
    if not filter_cfg:
        return True
    field = str(filter_cfg.get("source_field") or "").strip()
    values = _parse_filter_values(filter_cfg.get("values"))
    if not field:
        return True
    if not values:
        return True
    raw = _get_value(source_values, source_note, field)
    hay = str(raw or "").lower()
    if not hay:
        return False
    mode = str(filter_cfg.get("mode") or "contains").lower()
    if mode == "equals":
        return any(hay == v for v in values)
    return any(v in hay for v in values)


def _select_category(source_note, source_values: Dict[str, str], categories: List[Dict]) -> Optional[Dict]:
    for cat in categories:
        if not isinstance(cat, dict):
            continue
        filt = cat.get("filter") or {}
        if _matches_filter(source_note, source_values, filt):
            return cat
    return None


def convert_notes(cfg: Dict, manual: bool = False) -> Dict[str, int]:
    col = mw.col
    if not col:
        _LOGGER.warning("Collection not ready; aborting conversion")
        return {"created": 0, "skipped": 0}

    source_id = cfg.get("source_note_type_id")
    if source_id:
        source_ids = [source_id]
    else:
        source_ids = cfg.get("source_note_type_ids") or []
    if not source_ids:
        _LOGGER.info("No source note types configured")
        if manual:
            tooltip("No source note types selected.")
        return {"created": 0, "skipped": 0}

    categories = cfg.get("categories") or []
    if not categories:
        _LOGGER.info("No categories configured")
        if manual:
            tooltip("No categories configured.")
        return {"created": 0, "skipped": 0}
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
                source_values = _build_source_values(source_note, cfg)
                category = _select_category(source_note, source_values, categories)
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
                _apply_field_mapping(new_note, source_note, source_values, field_map, target_model, cfg)
                new_note.tags = _collect_tags(source_note, cfg, source_values)

                deck_id = col.decks.current()["id"]
                try:
                    col.add_note(new_note, deck_id)
                except TypeError:
                    col.addNote(new_note)

                _mark_source_note(source_note, cfg, source_values, linked_note=new_note)
                total_created += 1
    finally:
        mw.progress.finish()

    _LOGGER.info("Conversion done. created=%s skipped=%s", total_created, total_skipped)
    if manual:
        tooltip(f"Yomitan import: {total_created} created, {total_skipped} skipped.")
    return {"created": int(total_created), "skipped": int(total_skipped)}


def preview_preprocessing(cfg: Dict, limit: int = 10) -> List[Dict[str, str]]:
    col = mw.col
    if not col:
        return []

    source_id = cfg.get("source_note_type_id")
    if source_id:
        source_ids = [source_id]
    else:
        source_ids = cfg.get("source_note_type_ids") or []
    if not source_ids:
        return []

    categories = cfg.get("categories") or []
    tags_cfg = cfg.get("tags") or {}
    processed_tag = str(tags_cfg.get("processed_tag") or "").strip()

    try:
        target_count = max(1, int(limit))
    except Exception:
        target_count = 10

    out: List[Dict[str, str]] = []
    for source_model_id in source_ids:
        source_model = _get_target_model(col, source_model_id)
        if not source_model:
            continue
        model_name = str(source_model.get("name") or "")
        if not model_name:
            continue

        if processed_tag:
            query = f'note:"{model_name}" -tag:"{processed_tag}"'
        else:
            query = f'note:"{model_name}"'
        note_ids = col.find_notes(query)

        # fetch a small chunk from each model, keep output bounded globally
        for nid in note_ids[: max(20, target_count * 2)]:
            source_note = col.get_note(nid)
            source_values = _build_source_values(source_note, cfg)
            category = _select_category(source_note, source_values, categories)
            out.append(
                {
                    "nid": str(nid),
                    "model": model_name,
                    "category": str((category or {}).get("name") or "<no match>"),
                    "pos_before": str(
                        _get_field(source_note, "PartOfSpeech") or _get_field(source_note, "POS") or ""
                    ),
                    "pos_after": str(source_values.get("PartOfSpeech") or ""),
                    "selection_before": str(_get_field(source_note, "SelectionText") or ""),
                    "selection_after": str(source_values.get("SelectionText") or ""),
                    "glossary_first_before": str(
                        _get_field(source_note, "GlossaryFirst")
                        or _get_field(source_note, "GlossaryJMDictGerHTML")
                        or ""
                    ),
                    "glossary_first_after": str(source_values.get("GlossaryFirst") or ""),
                    "vocab": str(source_values.get("Vocab") or _get_field(source_note, "Vocab") or ""),
                }
            )
            if len(out) >= target_count:
                return out
    return out
