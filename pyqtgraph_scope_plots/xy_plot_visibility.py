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
from typing import Any, List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QTableWidgetItem
from pydantic import BaseModel

from .save_restore_model import HasSaveLoadConfig
from .signals_table import SignalsTable
from .xy_plot import XyPlotWidget, XyPlotTable, XyWindowModel


class XyVisibilityModel(XyWindowModel):
    hidden_data: List[Tuple[str, str]] = []  # x, y


class VisibilityXyPlotWidget(XyPlotWidget, HasSaveLoadConfig):
    """Mixin into XyPlotWidget that allows plots to be hidden."""

    _MODEL_BASES = [XyVisibilityModel]

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

    def _write_model(self, model: BaseModel) -> None:
        super()._write_model(model)
        assert isinstance(model, XyVisibilityModel)
        # model.ref_geo = [expr for expr, parsed in self._refgeo_fns]

    def _load_model(self, model: BaseModel) -> None:
        super()._load_model(model)
        assert isinstance(model, XyVisibilityModel)
        # while len(self._refgeo_fns) > 0:  # delete existing
        #     self.set_ref_geometry_fn("", 0, update=False)
        # for expr in model.ref_geo:
        #     try:
        #         self.set_ref_geometry_fn(expr, update=False)
        #     except Exception as e:
        #         print(f"failed to restore ref geometry fn {expr}: {e}")  # TODO better logging
        #
        # # bulk update
        # self._update()
        # self.sigXyDataItemsChanged.emit()

    def _update(self) -> None:
        super()._update()


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

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

    def _update(self) -> None:
        super()._update()
        assert isinstance(self._xy_plots, VisibilityXyPlotWidget)
        for row, xy_item in enumerate(self._xy_plots._xys):
            item = SignalsTable._create_noneditable_table_item()
            item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            item.setCheckState(Qt.CheckState.Checked)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row, self.COL_VISIBILITY, item)

    def _on_visibility_toggle(self, item: QTableWidgetItem) -> None:
        pass
