from typing import Dict, List, Optional

from aqt import mw
from aqt.qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QStandardItem,
    QStandardItemModel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from aqt.qt import Qt

from .conversion import DEFAULT_FIELD_MAPPING, VALUE_SOURCES


class CheckableComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        line = self.lineEdit()
        if isinstance(line, QLineEdit):
            line.setReadOnly(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setModel(QStandardItemModel(self))
        self.view().pressed.connect(self._toggle_item)
        self._update_display()

    def add_checkable_item(self, text: str, data):
        item = QStandardItem(text)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        item.setData(data, Qt.UserRole)
        item.setCheckState(Qt.Unchecked)
        self.model().appendRow(item)

    def checked_data(self) -> List:
        items = []
        for row in range(self.model().rowCount()):
            item = self.model().item(row)
            if item.checkState() == Qt.Checked:
                items.append(item.data(Qt.UserRole))
        return items

    def set_checked_data(self, values: List):
        values = set(values or [])
        for row in range(self.model().rowCount()):
            item = self.model().item(row)
            if item.data(Qt.UserRole) in values:
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
        self._update_display()

    def _toggle_item(self, index):
        item = self.model().itemFromIndex(index)
        if item.checkState() == Qt.Checked:
            item.setCheckState(Qt.Unchecked)
        else:
            item.setCheckState(Qt.Checked)
        self._update_display()

    def _update_display(self):
        count = len(self.checked_data())
        text = f"{count} ausgewaehlt" if count else "Keine ausgewaehlt"
        line = self.lineEdit()
        if isinstance(line, QLineEdit):
            line.setText(text)


class FieldMapWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._form = QFormLayout(self)
        self._combos = {}
        self._current_model = None

    def set_model(self, model, current_map: Optional[Dict]):
        self._current_model = model
        while self._form.rowCount():
            self._form.removeRow(0)
        self._combos.clear()

        if not model:
            self._form.addRow(QLabel("Bitte Notetyp waehlen."))
            return

        for field in model["flds"]:
            name = field["name"]
            combo = QComboBox(self)
            for key, label in VALUE_SOURCES:
                combo.addItem(label, key)
            desired = None
            if current_map and name in current_map:
                desired = current_map.get(name)
            elif name in DEFAULT_FIELD_MAPPING:
                desired = DEFAULT_FIELD_MAPPING[name]
            if desired:
                idx = combo.findData(desired)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            self._combos[name] = combo
            self._form.addRow(QLabel(name), combo)

    def get_mapping(self) -> Dict:
        mapping = {}
        for name, combo in self._combos.items():
            mapping[name] = combo.currentData()
        return mapping


class PosMappingTab(QWidget):
    def __init__(self, category: str, note_types: List[Dict], mapping: Dict, parent=None):
        super().__init__(parent)
        self._note_types = note_types
        self._mapping = mapping or {}
        self._current_field_map = self._mapping.get("field_map") or {}

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.note_type_combo = QComboBox(self)
        self.note_type_combo.addItem("(keiner)", None)
        for model in note_types:
            self.note_type_combo.addItem(model["name"], model["id"])

        current_id = self._mapping.get("note_type_id")
        if current_id:
            idx = self.note_type_combo.findData(current_id)
            if idx >= 0:
                self.note_type_combo.setCurrentIndex(idx)

        form.addRow(QLabel("Ziel-Notetyp"), self.note_type_combo)
        layout.addLayout(form)

        self.field_map_widget = FieldMapWidget(self)
        layout.addWidget(self.field_map_widget)

        self.note_type_combo.currentIndexChanged.connect(self._refresh_mapping)
        self._refresh_mapping()

    def _refresh_mapping(self):
        model = self._current_model()
        self.field_map_widget.set_model(model, self._current_field_map)

    def _current_model(self):
        model_id = self.note_type_combo.currentData()
        if not model_id:
            return None
        for model in self._note_types:
            if model["id"] == model_id:
                return model
        return None

    def get_value(self) -> Dict:
        return {
            "note_type_id": self.note_type_combo.currentData(),
            "field_map": self.field_map_widget.get_mapping(),
        }


class ConfigDialog(QDialog):
    def __init__(self, cfg: Dict, save_cb, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AJpC Yomitran Einstellungen")
        self._cfg = cfg
        self._save_cb = save_cb

        note_types = sorted(mw.col.models.all(), key=lambda m: m["name"].lower())

        root = QVBoxLayout(self)
        self.auto_sync = QCheckBox("Beim Sync automatisch ausfuehren")
        self.auto_sync.setChecked(bool(cfg.get("auto_on_sync", True)))
        root.addWidget(self.auto_sync)

        root.addWidget(QLabel("Quell-Notetypen (Yomitan-Importe):"))
        self.source_selector = CheckableComboBox(self)
        for model in note_types:
            self.source_selector.add_checkable_item(model["name"], model["id"])
        self.source_selector.set_checked_data(cfg.get("source_note_type_ids") or [])
        root.addWidget(self.source_selector)

        self.tabs = QTabWidget(self)
        self._tab_widgets = {}
        for key, label in (
            ("verb", "Verb"),
            ("adjective", "Adjektiv"),
            ("other", "Sonstige"),
        ):
            tab = PosMappingTab(key, note_types, cfg.get("pos_mappings", {}).get(key), self)
            self.tabs.addTab(tab, label)
            self._tab_widgets[key] = tab
        root.addWidget(self.tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, Qt.Horizontal)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_save(self):
        self._cfg["auto_on_sync"] = self.auto_sync.isChecked()
        self._cfg["source_note_type_ids"] = self.source_selector.checked_data()
        pos = self._cfg.get("pos_mappings") or {}
        for key, tab in self._tab_widgets.items():
            pos[key] = tab.get_value()
        self._cfg["pos_mappings"] = pos
        self._save_cb(self._cfg)
        self.accept()
