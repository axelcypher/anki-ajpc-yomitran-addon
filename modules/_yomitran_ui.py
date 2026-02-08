import copy
import json
from typing import Dict, List, Optional

from aqt import mw
from aqt.qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from aqt.qt import Qt
from aqt.utils import tooltip

from ._yomitran_conversion import DEFAULT_FIELD_MAPPING, build_value_sources


SETUP_TIPS = {
    "source_enabled": "Enable this source field for use in mappings and virtual fields.",
    "source_field": "Raw source field name from the selected Yomitan source note type.",
    "source_display_label": "Label shown in mapping dropdowns for this source field.",
    "virtual_id": "Stable internal key used by field mappings.",
    "virtual_name": "Display name shown in mapping dropdowns.",
    "virtual_type": (
        "Transformation type: copy/to_hepburn/to_tag uses Source field; "
        "fallback uses Primary+Fallback; note_link uses Link label."
    ),
    "virtual_source": "Source field consumed by copy/to_hepburn/to_tag.",
    "virtual_primary": "Primary source field for fallback type.",
    "virtual_fallback": "Fallback source field used when Primary is empty.",
    "virtual_link_label": "Link label used for note_link raw links.",
}

CATEGORY_TIPS = {
    "category_name": "Display name of this conversion category/tab.",
    "target_note_type": "Destination note type created from matching source notes.",
    "filter_source": "Source field used to decide whether this category applies.",
    "filter_values": "Match values separated by ';' or ','.",
    "filter_mode": "Contains: partial match. Equals: exact full-value match.",
    "field_map": "Map each target field to one source/virtual value.",
}

TAG_TRANSFORM_TIP = (
    "Tag transform JSON object.\n"
    "Keys:\n"
    "- mapping: raw_tag -> final_tag\n"
    "- drop: list of raw tags to remove\n"
    "- prefix: prefix for unmapped tags"
)

CONFIG_TIPS = {
    "run_on_sync": "Run conversion on sync start.",
    "run_on_card_added": "Run conversion when new notes/cards are added.",
    "source_note_type": "Yomitan import source note type used as conversion input.",
}


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.setParent(None)
        if child_layout is not None:
            _clear_layout(child_layout)


def _make_label(text: str, tip: str = "") -> QLabel:
    label = QLabel(text)
    if tip:
        label.setToolTip(tip)
    return label


class FieldMapWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._form = QFormLayout(self)
        self._combos: Dict[str, QComboBox] = {}
        self._current_model = None
        self._current_map: Dict[str, str] = {}
        self._value_sources = []

    def set_model(self, model, current_map: Optional[Dict], value_sources: List):
        self._current_model = model
        self._current_map = current_map or {}
        self._value_sources = value_sources
        self._rebuild()

    def _rebuild(self):
        _clear_layout(self._form)
        self._combos.clear()

        if not self._current_model:
            self._form.addRow(QLabel("Select a note type."))
            return

        for field in self._current_model["flds"]:
            name = field["name"]
            combo = QComboBox(self)
            for key, label in self._value_sources:
                combo.addItem(label, key)
            desired = self._current_map.get(name)
            if not desired and name in DEFAULT_FIELD_MAPPING:
                desired = DEFAULT_FIELD_MAPPING[name]
            if desired:
                idx = combo.findData(desired)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            self._combos[name] = combo
            self._form.addRow(QLabel(name), combo)

    def refresh_value_sources(self, value_sources: List):
        self._value_sources = value_sources
        for name, combo in self._combos.items():
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for key, label in value_sources:
                combo.addItem(label, key)
            if current is not None:
                idx = combo.findData(current)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    def get_mapping(self) -> Dict:
        mapping = {}
        for name, combo in self._combos.items():
            mapping[name] = combo.currentData()
        return mapping


class SourceFieldsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._rows = []
        self._display_label_min_width = 200
        self._display_label_max_width = 256

    def set_fields(self, fields: List[Dict]):
        _clear_layout(self._grid)
        self._rows = []
        self._grid.addWidget(_make_label("Enabled", SETUP_TIPS["source_enabled"]), 0, 0)
        self._grid.addWidget(_make_label("Field", SETUP_TIPS["source_field"]), 0, 1)
        self._grid.addWidget(_make_label("Display label", SETUP_TIPS["source_display_label"]), 0, 2)

        for idx, field in enumerate(fields, start=1):
            name = str(field.get("name") or "").strip()
            if not name:
                continue
            enabled = bool(field.get("enabled", True))
            label = str(field.get("label") or name)

            chk = QCheckBox(self)
            chk.setChecked(enabled)
            name_label = QLabel(name, self)
            name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label_edit = QLineEdit(label, self)
            label_edit.setMinimumWidth(self._display_label_min_width)
            label_edit.setMaximumWidth(self._display_label_max_width)

            self._grid.addWidget(chk, idx, 0)
            self._grid.addWidget(name_label, idx, 1)
            self._grid.addWidget(label_edit, idx, 2)
            self._rows.append({"name": name, "enabled": chk, "label": label_edit})

    def get_fields(self) -> List[Dict]:
        out = []
        for row in self._rows:
            name = row["name"]
            enabled = row["enabled"].isChecked()
            label = row["label"].text().strip() or name
            out.append({"name": name, "label": label, "enabled": enabled})
        return out

    def field_names(self, include_disabled: bool = True) -> List[str]:
        names = []
        for row in self._rows:
            if include_disabled or row["enabled"].isChecked():
                names.append(row["name"])
        return names


class VirtualFieldRow(QWidget):
    TYPE_LABELS = [
        ("copy", "Copy"),
        ("fallback", "Fallback"),
        ("to_hepburn", "To Hepburn"),
        ("to_tag", "To Tag"),
        ("note_link", "Note Link"),
    ]

    def __init__(self, source_fields: List[str], data: Dict, remove_cb, parent=None):
        super().__init__(parent)
        self._remove_cb = remove_cb
        self._source_fields = list(source_fields)
        self._col_width = 120

        layout = QGridLayout(self)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(4)

        self.id_edit = QLineEdit(str(data.get("id") or ""), self)
        self.name_edit = QLineEdit(str(data.get("name") or ""), self)
        self.type_combo = QComboBox(self)
        for key, label in self.TYPE_LABELS:
            self.type_combo.addItem(label, key)

        self.remove_btn = QPushButton("Remove", self)
        self.remove_btn.clicked.connect(lambda: self._remove_cb(self))

        self.id_edit.setFixedWidth(self._col_width)
        self.name_edit.setFixedWidth(self._col_width)
        self.type_combo.setFixedWidth(self._col_width)
        self.remove_btn.setFixedWidth(80)

        layout.addWidget(_make_label("ID", SETUP_TIPS["virtual_id"]), 0, 0)
        layout.addWidget(_make_label("Name", SETUP_TIPS["virtual_name"]), 0, 1)
        layout.addWidget(_make_label("Type", SETUP_TIPS["virtual_type"]), 0, 2)
        layout.addWidget(self.id_edit, 1, 0)
        layout.addWidget(self.name_edit, 1, 1)
        layout.addWidget(self.type_combo, 1, 2)
        layout.addWidget(self.remove_btn, 1, 3)

        self.source_combo = QComboBox(self)
        self.primary_combo = QComboBox(self)
        self.fallback_combo = QComboBox(self)
        self.label_edit = QLineEdit(str(data.get("label") or "Source"), self)
        for combo in (self.source_combo, self.primary_combo, self.fallback_combo):
            combo.setFixedWidth(self._col_width)
        self.label_edit.setFixedWidth(self._col_width)

        self.source_label = _make_label("Source field", SETUP_TIPS["virtual_source"])
        self.source_label.setParent(self)
        layout.addWidget(self.source_label, 2, 0)
        layout.addWidget(self.source_combo, 3, 0)
        self.primary_label = _make_label("Primary", SETUP_TIPS["virtual_primary"])
        self.primary_label.setParent(self)
        layout.addWidget(self.primary_label, 2, 0)
        layout.addWidget(self.primary_combo, 3, 0)
        self.fallback_label = _make_label("Fallback", SETUP_TIPS["virtual_fallback"])
        self.fallback_label.setParent(self)
        layout.addWidget(self.fallback_label, 2, 1)
        layout.addWidget(self.fallback_combo, 3, 1)
        self.link_label = _make_label("Link label", SETUP_TIPS["virtual_link_label"])
        self.link_label.setParent(self)
        layout.addWidget(self.link_label, 2, 0)
        layout.addWidget(self.label_edit, 3, 0)

        self.set_source_fields(source_fields)

        desired_type = str(data.get("type") or "copy")
        idx = self.type_combo.findData(desired_type)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)

        self._set_combo_value(self.source_combo, data.get("source"))
        self._set_combo_value(self.primary_combo, data.get("primary"))
        self._set_combo_value(self.fallback_combo, data.get("fallback"))

        self.type_combo.currentIndexChanged.connect(self._update_visibility)
        self._update_visibility()

    def _set_combo_value(self, combo: QComboBox, value: Optional[str]):
        if value is None:
            return
        idx = combo.findData(value)
        if idx < 0:
            idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def set_source_fields(self, names: List[str]):
        self._source_fields = list(names)
        for combo in (self.source_combo, self.primary_combo, self.fallback_combo):
            current = combo.currentData() or combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            for name in self._source_fields:
                combo.addItem(name, name)
            if current:
                self._set_combo_value(combo, current)
            combo.blockSignals(False)

    def _update_visibility(self):
        vtype = self.type_combo.currentData()
        for widget in (
            self.source_combo,
            self.primary_combo,
            self.fallback_combo,
            self.label_edit,
            self.source_label,
            self.primary_label,
            self.fallback_label,
            self.link_label,
        ):
            widget.setVisible(False)

        def show_row(widgets):
            for widget in widgets:
                widget.setVisible(True)

        if vtype in ("copy", "to_hepburn", "to_tag"):
            show_row([self.source_label, self.source_combo])
        elif vtype == "fallback":
            show_row(
                [
                    self.primary_label,
                    self.primary_combo,
                    self.fallback_label,
                    self.fallback_combo,
                ]
            )
        elif vtype == "note_link":
            show_row([self.link_label, self.label_edit])

    def get_value(self) -> Dict:
        vtype = self.type_combo.currentData()
        data = {
            "id": self.id_edit.text().strip(),
            "name": self.name_edit.text().strip() or self.id_edit.text().strip(),
            "type": vtype,
        }
        if vtype in ("copy", "to_hepburn", "to_tag"):
            data["source"] = self.source_combo.currentData()
        elif vtype == "fallback":
            data["primary"] = self.primary_combo.currentData()
            data["fallback"] = self.fallback_combo.currentData()
        elif vtype == "note_link":
            data["label"] = self.label_edit.text().strip() or "Source"
        return data


class VirtualFieldsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: List[VirtualFieldRow] = []
        self._layout = QVBoxLayout(self)
        self._rows_layout = QVBoxLayout()
        self._layout.addLayout(self._rows_layout)
        self._add_btn = QPushButton("Add virtual field", self)
        self._add_btn.clicked.connect(self._add_row)
        self._layout.addWidget(self._add_btn)
        self._source_fields: List[str] = []

    def set_source_fields(self, names: List[str]):
        self._source_fields = list(names)
        for row in self._rows:
            row.set_source_fields(self._source_fields)

    def set_fields(self, fields: List[Dict]):
        for row in self._rows:
            row.setParent(None)
        self._rows = []
        for field in fields:
            self._add_row(field)

    def _add_row(self, data: Optional[Dict] = None):
        # QPushButton.clicked emits a bool; ignore non-dict payloads.
        if not isinstance(data, dict):
            data = {"id": "", "name": "", "type": "copy"}
        row = VirtualFieldRow(self._source_fields, data, self._remove_row, self)
        self._rows.append(row)
        self._rows_layout.addWidget(row)

    def _remove_row(self, row: VirtualFieldRow):
        if row in self._rows:
            self._rows.remove(row)
            row.setParent(None)

    def get_fields(self) -> List[Dict]:
        out = []
        for row in self._rows:
            val = row.get_value()
            if not val.get("id"):
                continue
            out.append(val)
        return out


class SetupTab(QWidget):
    def __init__(self, cfg: Dict, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.setSpacing(10)
        layout.addLayout(row)

        source_group = QGroupBox("Source fields", self)
        source_group.setToolTip(
            "Configure source fields from the selected Yomitan source note type."
        )
        source_layout = QVBoxLayout(source_group)
        self.source_fields_widget = SourceFieldsWidget(source_group)
        source_layout.addWidget(self.source_fields_widget)
        row.addWidget(source_group, 3)

        virtual_group = QGroupBox("Virtual fields", self)
        virtual_group.setToolTip(
            "Define computed values that can be used in category field mappings."
        )
        virtual_layout = QVBoxLayout(virtual_group)
        self.virtual_fields_widget = VirtualFieldsWidget()
        virtual_layout.addWidget(self.virtual_fields_widget)
        row.addWidget(virtual_group, 2)
        layout.addStretch(1)

        self.set_values(cfg)

    def set_values(self, cfg: Dict):
        self.source_fields_widget.set_fields(cfg.get("source_fields") or [])
        self.virtual_fields_widget.set_source_fields(self.source_fields_widget.field_names(True))
        self.virtual_fields_widget.set_fields(cfg.get("virtual_fields") or [])

    def get_source_fields(self) -> List[Dict]:
        return self.source_fields_widget.get_fields()

    def get_virtual_fields(self) -> List[Dict]:
        return self.virtual_fields_widget.get_fields()

    def refresh_source_fields(self, fields: List[Dict]):
        self.source_fields_widget.set_fields(fields)
        self.virtual_fields_widget.set_source_fields(self.source_fields_widget.field_names(True))


class CategoryTab(QWidget):
    def __init__(
        self,
        category: Dict,
        note_types: List[Dict],
        value_sources_fn,
        source_fields_fn,
        name_changed_cb,
        parent=None,
    ):
        super().__init__(parent)
        self._note_types = note_types
        self._value_sources_fn = value_sources_fn
        self._source_fields_fn = source_fields_fn
        self._name_changed_cb = name_changed_cb
        self._category = category or {}
        self._current_field_map = self._category.get("field_map") or {}

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit(str(self._category.get("name") or ""), self)
        self.name_edit.textChanged.connect(self._on_name_changed)
        category_name_label = _make_label("Category name", CATEGORY_TIPS["category_name"])
        form.addRow(category_name_label, self.name_edit)

        self.note_type_combo = QComboBox(self)
        self.note_type_combo.addItem("(none)", None)
        for model in note_types:
            self.note_type_combo.addItem(model["name"], model["id"])
        current_id = self._category.get("note_type_id")
        if current_id:
            idx = self.note_type_combo.findData(current_id)
            if idx >= 0:
                self.note_type_combo.setCurrentIndex(idx)
        target_note_type_label = _make_label("Target note type", CATEGORY_TIPS["target_note_type"])
        form.addRow(target_note_type_label, self.note_type_combo)

        self.filter_source_combo = QComboBox(self)
        self.filter_source_combo.addItem("(none)", "")
        for name in self._source_fields_fn(True):
            self.filter_source_combo.addItem(name, name)
        filter_cfg = self._category.get("filter") or {}
        self._set_combo_value(self.filter_source_combo, filter_cfg.get("source_field"))

        self.filter_values_edit = QLineEdit(str(filter_cfg.get("values") or ""), self)
        self.filter_values_edit.setPlaceholderText("godan; ichidan")

        self.filter_mode_combo = QComboBox(self)
        self.filter_mode_combo.addItem("Contains", "contains")
        self.filter_mode_combo.addItem("Equals", "equals")
        self._set_combo_value(self.filter_mode_combo, filter_cfg.get("mode") or "contains")

        filter_source_label = _make_label("Filter source field", CATEGORY_TIPS["filter_source"])
        filter_values_label = _make_label("Filter values", CATEGORY_TIPS["filter_values"])
        filter_mode_label = _make_label("Filter match", CATEGORY_TIPS["filter_mode"])
        form.addRow(filter_source_label, self.filter_source_combo)
        form.addRow(filter_values_label, self.filter_values_edit)
        form.addRow(filter_mode_label, self.filter_mode_combo)

        layout.addLayout(form)

        self.field_map_widget = FieldMapWidget(self)
        self.field_map_widget.setToolTip(CATEGORY_TIPS["field_map"])
        layout.addWidget(self.field_map_widget)
        layout.addStretch(1)

        self.note_type_combo.currentIndexChanged.connect(self._refresh_mapping)
        self._refresh_mapping()

    def _set_combo_value(self, combo: QComboBox, value: Optional[str]):
        if value is None:
            return
        idx = combo.findData(value)
        if idx < 0:
            idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _on_name_changed(self, text: str):
        if self._name_changed_cb:
            self._name_changed_cb(text.strip() or "Category")

    def _current_model(self):
        model_id = self.note_type_combo.currentData()
        if not model_id:
            return None
        for model in self._note_types:
            if model["id"] == model_id:
                return model
        return None

    def _refresh_mapping(self):
        model = self._current_model()
        self.field_map_widget.set_model(model, self._current_field_map, self._value_sources_fn())

    def refresh_sources(self):
        current = self.filter_source_combo.currentData()
        self.filter_source_combo.blockSignals(True)
        self.filter_source_combo.clear()
        self.filter_source_combo.addItem("(none)", "")
        for name in self._source_fields_fn(True):
            self.filter_source_combo.addItem(name, name)
        self._set_combo_value(self.filter_source_combo, current)
        self.filter_source_combo.blockSignals(False)
        self.field_map_widget.refresh_value_sources(self._value_sources_fn())

    def get_value(self) -> Dict:
        values_raw = self.filter_values_edit.text().strip()
        filter_cfg = {
            "source_field": self.filter_source_combo.currentData() or "",
            "values": values_raw,
            "mode": self.filter_mode_combo.currentData(),
        }
        return {
            "id": self._category.get("id") or self.name_edit.text().strip().lower().replace(" ", "_"),
            "name": self.name_edit.text().strip() or "Category",
            "note_type_id": self.note_type_combo.currentData(),
            "filter": filter_cfg,
            "field_map": self.field_map_widget.get_mapping(),
        }


class TagTransformTab(QWidget):
    def __init__(self, current: Dict, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        tag_label = _make_label("Tag transform JSON (mapping / drop).", TAG_TRANSFORM_TIP)
        layout.addWidget(tag_label)
        self.editor = QPlainTextEdit(self)
        self.editor.setToolTip(TAG_TRANSFORM_TIP)
        self.editor.setPlainText(json.dumps(current, ensure_ascii=False, indent=2))
        layout.addWidget(self.editor)

    def get_value(self) -> Optional[Dict]:
        raw = self.editor.toPlainText().strip()
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except Exception:
            tooltip("Tag transform JSON is invalid.")
            return None
        if not isinstance(value, dict):
            tooltip("Tag transform JSON must be an object.")
            return None
        return value


class ConfigPanel(QWidget):
    def __init__(self, cfg: Dict, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._category_tabs: List[CategoryTab] = []

        note_types = sorted(mw.col.models.all(), key=lambda m: m["name"].lower())

        root = QVBoxLayout(self)
        self.run_on_sync = QCheckBox("Run on sync")
        self.run_on_sync.setToolTip(CONFIG_TIPS["run_on_sync"])
        self.run_on_sync.setChecked(bool(cfg.get("run_on_sync", cfg.get("auto_on_sync", True))))
        root.addWidget(self.run_on_sync)

        self.run_on_card_added = QCheckBox("Run on card added")
        self.run_on_card_added.setToolTip(CONFIG_TIPS["run_on_card_added"])
        self.run_on_card_added.setChecked(bool(cfg.get("run_on_card_added", False)))
        root.addWidget(self.run_on_card_added)

        source_type_label = _make_label(
            "Source note type (Yomitan import):", CONFIG_TIPS["source_note_type"]
        )
        root.addWidget(source_type_label)
        self.source_selector = QComboBox(self)
        self.source_selector.setToolTip(CONFIG_TIPS["source_note_type"])
        self.source_selector.addItem("(none)", None)
        for model in note_types:
            self.source_selector.addItem(model["name"], model["id"])

        selected_id = cfg.get("source_note_type_id")
        if not selected_id:
            legacy = cfg.get("source_note_type_ids") or []
            if legacy:
                selected_id = legacy[0]
        if selected_id:
            idx = self.source_selector.findData(selected_id)
            if idx >= 0:
                self.source_selector.setCurrentIndex(idx)
        root.addWidget(self.source_selector)
        self.tabs = QTabWidget(self)
        self.setup_tab = SetupTab(cfg, self)
        self.tabs.addTab(self.setup_tab, "Setup")

        self._note_types = note_types
        for category in cfg.get("categories") or []:
            self._add_category_tab(category)

        self.tag_tab = TagTransformTab(cfg.get("tag_transform") or {}, self)
        self.tabs.addTab(self.tag_tab, "Tag Transform")
        root.addWidget(self.tabs)

        button_row = QHBoxLayout()
        self.add_category_btn = QPushButton("Add category", self)
        self.remove_category_btn = QPushButton("Remove category", self)
        self.add_category_btn.clicked.connect(self._on_add_category)
        self.remove_category_btn.clicked.connect(self._on_remove_category)
        button_row.addWidget(self.add_category_btn)
        button_row.addWidget(self.remove_category_btn)
        root.addLayout(button_row)

        self.source_selector.currentIndexChanged.connect(self._on_source_changed)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._on_source_changed()

    def _value_sources(self) -> List:
        temp_cfg = {
            "source_fields": self.setup_tab.get_source_fields(),
            "virtual_fields": self.setup_tab.get_virtual_fields(),
        }
        return build_value_sources(temp_cfg)

    def _source_field_names(self, include_disabled: bool = True) -> List[str]:
        if include_disabled:
            return self.setup_tab.source_fields_widget.field_names(True)
        return self.setup_tab.source_fields_widget.field_names(False)

    def _add_category_tab(self, category: Dict):
        tab = CategoryTab(
            category,
            self._note_types,
            self._value_sources,
            self._source_field_names,
            lambda name: self._rename_category_tab(tab, name),
            self,
        )
        label = category.get("name") or "Category"
        insert_at = self.tabs.count()
        if hasattr(self, "tag_tab"):
            idx = self.tabs.indexOf(self.tag_tab)
            if idx >= 0:
                insert_at = idx
        self.tabs.insertTab(insert_at, tab, label)
        self._category_tabs.append(tab)

    def _rename_category_tab(self, tab: CategoryTab, name: str):
        idx = self.tabs.indexOf(tab)
        if idx >= 0:
            self.tabs.setTabText(idx, name)

    def _on_add_category(self):
        new_cat = {
            "id": "category",
            "name": "Category",
            "note_type_id": None,
            "filter": {"source_field": "", "values": "", "mode": "contains"},
            "field_map": {},
        }
        self._add_category_tab(new_cat)
        self.tabs.setCurrentWidget(self._category_tabs[-1])

    def _on_remove_category(self):
        widget = self.tabs.currentWidget()
        if widget in self._category_tabs:
            idx = self.tabs.indexOf(widget)
            if idx >= 0:
                self.tabs.removeTab(idx)
            self._category_tabs.remove(widget)
            widget.setParent(None)

    def _on_source_changed(self):
        model = None
        model_id = self.source_selector.currentData()
        for m in self._note_types:
            if m["id"] == model_id:
                model = m
                break
        fields = []
        existing = {f.get("name"): f for f in self._cfg.get("source_fields") or []}
        if model:
            for fld in model["flds"]:
                name = fld["name"]
                if name in existing:
                    fields.append(existing[name])
                else:
                    fields.append({"name": name, "label": name, "enabled": True})
        self.setup_tab.refresh_source_fields(fields)
        self.setup_tab.virtual_fields_widget.set_source_fields(self._source_field_names(True))
        for tab in self._category_tabs:
            tab.refresh_sources()

    def _on_tab_changed(self, _idx: int):
        widget = self.tabs.currentWidget()
        if widget in self._category_tabs:
            widget.refresh_sources()

    def collect_config(self, errors: Optional[List[str]] = None) -> Optional[Dict]:
        tag_transform = self.tag_tab.get_value()
        if tag_transform is None:
            if errors is not None:
                errors.append("Yomitran: tag transform JSON is invalid.")
            return None

        out_cfg = copy.deepcopy(self._cfg)

        out_cfg["run_on_sync"] = self.run_on_sync.isChecked()
        out_cfg["run_on_card_added"] = self.run_on_card_added.isChecked()
        out_cfg.pop("auto_on_sync", None)

        selected_id = self.source_selector.currentData()
        out_cfg["source_note_type_id"] = selected_id
        out_cfg.pop("source_note_type_ids", None)

        out_cfg["source_fields"] = self.setup_tab.get_source_fields()
        out_cfg["virtual_fields"] = self.setup_tab.get_virtual_fields()
        out_cfg["categories"] = [tab.get_value() for tab in self._category_tabs]
        out_cfg["tag_transform"] = tag_transform
        return out_cfg


class ConfigDialog(QDialog):
    def __init__(self, cfg: Dict, save_cb, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AJpC Yomitran Settings")
        self._save_cb = save_cb

        root = QVBoxLayout(self)
        self.panel = ConfigPanel(cfg, self)
        root.addWidget(self.panel)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_save(self):
        errors: List[str] = []
        next_cfg = self.panel.collect_config(errors)
        if next_cfg is None:
            if errors:
                tooltip(errors[0])
            return
        self._save_cb(next_cfg)
        self.accept()
