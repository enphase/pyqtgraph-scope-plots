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
import bisect
from typing import Dict, List, Any, Mapping, Tuple, Optional, Set

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import QSignalBlocker
from PySide6.QtGui import QAction, Qt, QDoubleValidator
from PySide6.QtWidgets import QTableWidgetItem, QMenu, QStyledItemDelegate, QLineEdit, QWidget, QHeaderView
from pydantic import BaseModel

from .cache_dict import IdentityCacheDict
from .multi_plot_widget import LinkedMultiPlotWidget, MultiPlotWidget
from .save_restore_model import DataTopModel, HasSaveLoadDataConfig, BaseTopModel
from .signals_table import ContextMenuSignalsTable, SignalsTable
from .util import not_none


class VisibilityPlotWidget(MultiPlotWidget):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

        self._hidden_data: Set[str] = set()  # set of data traces that are invisible

    def hide_data_item(self, data_items: List[str], hidden: bool = True) -> None:
        self._hidden_data.update(data_items)
        # TODO hide / unhide existing PlotItems

    # TODO hook on init to hide / unhide plotitems


class VisibilityToggleSignalsTable(SignalsTable):
    """Mixin into SignalsTable that adds a UI to time-shift a signal.
    This acts as the data store and transformer to apply the time-shift, but the actual
    values are set externally (by a function call, typically from the top-level coordinator
    that gets its data from the user dragging a plot line)."""

    COL_VISIBILITY = -1

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

    def _pre_cols(self) -> int:
        self.COL_VISIBILITY = super()._pre_cols()
        return self.COL_VISIBILITY + 1

    def _init_table(self) -> None:
        super()._init_table()
        self.horizontalHeader().setSectionResizeMode(self.COL_VISIBILITY, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(self.COL_VISIBILITY, 50)
        self.setHorizontalHeaderItem(self.COL_VISIBILITY, QTableWidgetItem("Visible"))

    def _update(self) -> None:
        super()._update()
        for row, (_, (_, plot_type)) in enumerate(self._plots._data_items.items()):
            item = self.item(row, self.COL_VISIBILITY)
            if plot_type == MultiPlotWidget.PlotType.DEFAULT:
                item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            else:
                item.setFlags(Qt.ItemFlag.ItemIsUserCheckable)  # other plots not disable-able
            item.setCheckState(Qt.CheckState.Checked)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
