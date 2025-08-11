# Copyright 2025 Enphase Energy, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
import os
from functools import partial
from typing import Dict, List, cast, Callable, Optional

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
        self._load_hotkey_actions: List[QAction] = []
        self._settings_obj = settings
        self._config_key = config_key
        self._load_fn = load_fn
        self._loaded_config_abspath = ""  # of last loaded config file, even if it has changed

    def _settings(self) -> QSettings:  # hook for unit testing
        return self._settings_obj

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

    def _to_model(self) -> RecentsModel:
        recents_val = cast(str, self._settings().value(self._config_key, ""))
        try:
            return RecentsModel.model_validate(RecentsModel(**yaml.safe_load(recents_val)))
        except (yaml.YAMLError, TypeError, ValidationError):
            return RecentsModel()

    def populate_recents_menu(self, menu: QMenu) -> None:
        """Add recents (including the item to bind a hotkey) to a menu."""
        recents = self._to_model()
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
        recents = self._to_model()

        hotkey, ok = QInputDialog.getInt(parent, "Set Hotkey Slot", "", value=0, minValue=0, maxValue=9)
        if not ok:
            return

        if self._loaded_config_abspath in recents.recents:
            recents.recents.remove(self._loaded_config_abspath)
        recents.hotkeys[hotkey] = self._loaded_config_abspath
        self._settings().setValue(self._config_key, yaml.dump(recents.model_dump(), sort_keys=False))

    def _load_hotkey_slot(self, slot: int) -> None:
        recents = self._to_model()
        target = recents.hotkeys.get(slot, None)
        if target is not None:
            self._load_fn(target)

    def file_changed(self, filename: Optional[str]) -> None:
        """Call this when a file is opened or saved, to tell the recents manager the currently open file.
        Use None to clear the opened file, eg on a new file."""
        if filename is None:  # only clear the currently open file
            self._loaded_config_abspath = ""
            return

        filename = os.path.abspath(filename)  # standardize to abspath
        self._loaded_config_abspath = filename

        recents = self._to_model()
        if filename in recents.hotkeys.values():
            return  # don't overwrite hotkeys
        if filename in recents.recents:
            recents.recents.remove(filename)
        recents.recents.insert(0, filename)
        excess_recents = len(recents.recents) + len(recents.hotkeys) - self._RECENTS_MAX
        if excess_recents > 0:
            recents.recents = recents.recents[:-excess_recents]

        self._settings().setValue(self._config_key, yaml.dump(recents.model_dump(), sort_keys=False))
