import copy

DEFAULT_CONFIG = {
    "auto_on_sync": True,
    "source_note_type_ids": [],
    "pos_mappings": {
        "verb": {"note_type_id": None, "field_map": {}},
        "adjective": {"note_type_id": None, "field_map": {}},
        "other": {"note_type_id": None, "field_map": {}},
    },
    "hepburn": {"engine": "pykakasi", "fallback": "simple"},
    "tags": {
        "processed_tag": "_intern::yomitan::processed",
        "export_tag": "_intern::yomitan_export",
        "link_tag_prefix": "_intern::yomitan::VOCAB_AUS_DEM_ES_STAMMT",
    },
}


def merge_config(default: dict, custom: dict) -> dict:
    if custom is None:
        return copy.deepcopy(default)
    merged = copy.deepcopy(default)
    for key, value in custom.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged
