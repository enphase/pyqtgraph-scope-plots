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
from typing import Any, List, Tuple, Set, Optional

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import QHeaderView, QTableWidgetItem
from pydantic import BaseModel

from .util import HasSaveLoadConfig
from .signals_table import SignalsTable
from .xy_plot import XyPlotWidget, XyPlotTable, XyWindowModel


class XyVisibilityStateModel(XyWindowModel):
    hidden_data: Optional[List[Tuple[str, str]]] = []  # x, y


class VisibilityXyPlotWidget(XyPlotWidget, HasSaveLoadConfig):
    """Mixin into XyPlotWidget that allows plots to be hidden."""

    _MODEL_BASES = [XyVisibilityStateModel]

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._hidden_data: Set[Tuple[str, str]] = set()

    def _write_model(self, model: BaseModel) -> None:
        super()._write_model(model)
        assert isinstance(model, XyVisibilityStateModel)
        model.hidden_data = sorted(list(self._hidden_data))

    def _load_model(self, model: BaseModel) -> None:
        super()._load_model(model)
        assert isinstance(model, XyVisibilityStateModel)
        if model.hidden_data is not None:
            self._hidden_data = set(model.hidden_data)

    def hide_xys(self, xys: List[Tuple[str, str]], hidden: bool = True) -> None:
        if hidden:
            self._hidden_data.update(xys)
        else:
            self._hidden_data.difference_update(xys)

        for xy in xys:
            for curve in self._xy_curves.get(xy, []):
                if hidden:
                    curve.hide()
                else:
                    curve.show()

    def _update(self) -> None:
        super()._update()  # all curves refreshed and start shown
        for hidden_xy in self._hidden_data:
            for curve in self._xy_curves.get(hidden_xy, []):
                curve.hide()


class VisibilityXyPlotTable(XyPlotTable):
    """Mixin into XyPlotTable that adds a visibility checkbox column"""

    COL_VISIBILITY = -1

    def _pre_cols(self) -> int:
        self.COL_VISIBILITY = super()._pre_cols()
        return self.COL_VISIBILITY + 1

    def _init_table(self) -> None:
        super()._init_table()
        self.horizontalHeader().setSectionResizeMode(self.COL_VISIBILITY, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(self.COL_VISIBILITY, 50)
        self.setHorizontalHeaderItem(self.COL_VISIBILITY, QTableWidgetItem("Visible"))
        self.itemChanged.connect(self._on_visibility_toggle)

    def _update(self) -> None:
        super()._update()
        assert isinstance(self._xy_plots, VisibilityXyPlotWidget)
        with QSignalBlocker(self):  # needed to prevent infinite-loop updating
            for row, xy_item in enumerate(self._xy_plots._xys):
                item = SignalsTable._create_noneditable_table_item()
                item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                if xy_item in self._xy_plots._hidden_data:  # TODO update might be part of a faster loop
                    item.setCheckState(Qt.CheckState.Unchecked)
                else:
                    item.setCheckState(Qt.CheckState.Checked)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.setItem(row, self.COL_VISIBILITY, item)

    def _on_visibility_toggle(self, item: QTableWidgetItem) -> None:
        assert isinstance(self._xy_plots, VisibilityXyPlotWidget)
        if item.column() != self.COL_VISIBILITY or item.row() >= len(self._xy_plots._xys):
            return
        self._xy_plots.hide_xys([self._xy_plots._xys[item.row()]], item.checkState() == Qt.CheckState.Unchecked)
