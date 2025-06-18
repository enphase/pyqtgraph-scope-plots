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
from typing import List, Any, Set, Optional

from PySide6.QtCore import QSignalBlocker
from PySide6.QtGui import Qt
from PySide6.QtWidgets import QTableWidgetItem, QHeaderView
from pydantic import BaseModel

from .multi_plot_widget import MultiPlotWidget
from .util import HasSaveLoadDataConfig, BaseTopModel, DataTopModel
from .signals_table import SignalsTable


class VisibilityDataStateModel(DataTopModel):
    hidden: Optional[bool] = None


class VisibilityPlotWidget(MultiPlotWidget, HasSaveLoadDataConfig):
    _DATA_MODEL_BASES = [VisibilityDataStateModel]

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

        self._hidden_data: Set[str] = set()  # set of data traces that are invisible

    def _write_model(self, model: BaseModel) -> None:
        assert isinstance(model, BaseTopModel)
        super()._write_model(model)
        for data_name, data_model in model.data.items():
            assert isinstance(data_model, VisibilityDataStateModel)
            data_model.hidden = data_name in self._hidden_data

    def _load_model(self, model: BaseModel) -> None:
        assert isinstance(model, BaseTopModel)
        super()._load_model(model)
        for data_name, data_model in model.data.items():
            assert isinstance(data_model, VisibilityDataStateModel)
            if data_model.hidden is not None:
                self.hide_data_items([data_name], data_model.hidden, update=False)

    def hide_data_items(self, data_items: List[str], hidden: bool = True, update: bool = True) -> None:
        if hidden:
            self._hidden_data.update(data_items)
        else:
            self._hidden_data.difference_update(data_items)

        if update:
            for data_item in data_items:
                for curve in self._data_curves.get(data_item, []):
                    if hidden:
                        curve.hide()
                    else:
                        curve.show()

    def _update_plots(self) -> None:
        super()._update_plots()
        for data_item in self._hidden_data:
            for curve in self._data_curves.get(data_item, []):
                curve.hide()


class VisibilityToggleSignalsTable(SignalsTable):
    """Mixin into SignalsTable that adds a visibility checkbox to a signal,
    allowing users to quickly toggle a signal on/off."""

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
        assert isinstance(self._plots, VisibilityPlotWidget)
        with QSignalBlocker(self):  # prevent updating state
            for row, (data_item, (_, plot_type)) in enumerate(self._plots._data_items.items()):
                item = self.item(row, self.COL_VISIBILITY)
                if data_item in self._plots._hidden_data:
                    item.setCheckState(Qt.CheckState.Unchecked)
                else:
                    item.setCheckState(Qt.CheckState.Checked)
                if plot_type == MultiPlotWidget.PlotType.DEFAULT:
                    item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                else:
                    item.setFlags(Qt.ItemFlag.ItemIsUserCheckable)  # other plots not disable-able
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

    def _on_visibility_toggle(self, item: QTableWidgetItem) -> None:
        if item.column() != self.COL_VISIBILITY or not item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
            return  # not ItemIsUserCheckable means it is in a pre-init state
        assert isinstance(self._plots, VisibilityPlotWidget)
        data_name = list(self._data_items.keys())[item.row()]
        self._plots.hide_data_items([data_name], item.checkState() == Qt.CheckState.Unchecked)
