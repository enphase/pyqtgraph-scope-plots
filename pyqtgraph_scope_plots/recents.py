import os
from functools import partial
from typing import Any, Dict, List, cast, Callable

import yaml
from PySide6.QtCore import QSettings, QKeyCombination
from PySide6.QtGui import QAction, Qt
from PySide6.QtWidgets import QWidget, QInputDialog, QMenu
from pydantic import BaseModel, ValidationError


class RecentsModel(BaseModel):
    """Data storage model for recents"""

    hotkeys: Dict[int, str] = {}  # hotkey number -> file
    recents: List[str] = []  # most recent first


class RecentsManager:
    """Class that manages recents, providing API hooks"""

    _RECENTS_MAX = 9  # hotkeys + recents is pruned to this count

    def __init__(self, settings: QSettings, config_key: str, load_fn: Callable[[str], None]) -> None:
        self._load_hotkey_actions = []
        self._settings = settings
        self._config_key = config_key
        self._load_fn = load_fn

    def bind_hotkeys(self, widget: QWidget) -> None:
        """Binds recents-loading hotkeys to the specified widget."""
        for i in range(10):
            load_hotkey_action = QAction(f"", widget)
            load_hotkey_action.setShortcut(
                QKeyCombination(Qt.KeyboardModifier.ControlModifier, Qt.Key(Qt.Key.Key_0 + i))
            )
            load_hotkey_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            load_hotkey_action.triggered.connect(partial(self._load_hotkey_slot, i))
            widget.addAction(load_hotkey_action)
            self._load_hotkey_actions.append(load_hotkey_action)

    def _get_recents(self) -> RecentsModel:
        recents_val = cast(str, self._settings.value(self._config_key, ""))
        try:
            return RecentsModel.model_validate(RecentsModel(**yaml.safe_load(recents_val)))
        except (yaml.YAMLError, TypeError, ValidationError):
            return RecentsModel()

    def populate_recents_menu(self, menu: QMenu) -> None:
        """Add recents (including the item to bind a hotkey) to a menu."""
        recents = self._get_recents()
        for hotkey, recent in sorted(recents.hotkeys.items(), key=lambda x: x[0]):
            load_hotkey_action = self._load_hotkey_actions[hotkey]  # crash on invalid index
            load_hotkey_action.setText(f"{os.path.split(recent)[1]}")
            menu.addAction(load_hotkey_action)

        for recent in recents.recents:
            load_action = QAction(f"{os.path.split(recent)[1]}", menu)
            load_action.triggered.connect(partial(self._load_fn, recent))
            menu.addAction(load_action)

        menu.addSeparator()
        set_hotkey_action = QAction("Set Hotkey", menu)
        set_hotkey_action.triggered.connect(partial(self._on_set_hotkey, menu))
        if self._loaded_config_abspath:
            set_hotkey_action.setText(f"Set Hotkey for {os.path.split(self._loaded_config_abspath)[1]}")
        else:
            set_hotkey_action.setDisabled(True)
        menu.addAction(set_hotkey_action)

    def _on_set_hotkey(self, parent: QWidget) -> None:
        assert self._loaded_config_abspath  # shouldn't be triggerable unless something loaded
        recents = self._get_recents()

        hotkey, ok = QInputDialog.getInt(parent, "Set Hotkey Slot", "", value=0, minValue=0, maxValue=9)
        if not ok:
            return

        if self._loaded_config_abspath in recents.recents:
            recents.recents.remove(self._loaded_config_abspath)
        recents.hotkeys[hotkey] = self._loaded_config_abspath
        self._settings.setValue(self._config_key, yaml.dump(recents.model_dump(), sort_keys=False))

    def _load_hotkey_slot(self, slot: int) -> None:
        recents = self._get_recents()
        target = recents.hotkeys.get(slot, None)
        if target is not None:
            self._load_fn(target)

    def append_recent(self, filename: str) -> None:
        recents = self._get_recents()
        if self._loaded_config_abspath in recents.hotkeys.values():
            return  # don't overwrite hotkeys
        if self._loaded_config_abspath in recents.recents:
            recents.recents.remove(self._loaded_config_abspath)
        recents.recents.insert(0, self._loaded_config_abspath)
        excess_recents = len(recents.recents) + len(recents.hotkeys) - self._RECENTS_MAX
        if excess_recents > 0:
            recents.recents = recents.recents[:-excess_recents]

        self._settings.setValue(self._config_key, yaml.dump(recents.model_dump(), sort_keys=False))
