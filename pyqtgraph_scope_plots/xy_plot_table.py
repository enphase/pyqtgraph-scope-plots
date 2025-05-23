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

from typing import Any

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget, QMenu

from .signals_table import ContextMenuSignalsTable


class XyTable(ContextMenuSignalsTable):
    """Mixin into SignalsTable that adds the option to open an XY plot in a separate window."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._xy_action = QAction("Create X-Y Plot", self)
        self._xy_action.triggered.connect(self._on_xy)

    def _populate_context_menu(self, menu: QMenu) -> None:
        super()._populate_context_menu(menu)
        menu.addAction(self._xy_action)

    def _on_xy(self) -> QWidget:
        """Creates an XY plot with the selected signal(s) and returns the new plot."""
        pass
