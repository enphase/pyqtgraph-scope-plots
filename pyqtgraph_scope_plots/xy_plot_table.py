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
from functools import partial
from typing import Any, List, Optional, Type

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QMessageBox, QWidget
from pydantic import BaseModel, create_model

from .util import BaseTopModel, HasSaveLoadDataConfig
from .signals_table import ContextMenuSignalsTable, DraggableSignalsTable
from .xy_plot import BaseXyPlot, XyWindowModel
from .xy_plot_splitter import XyPlotSplitter


class XyTableStateModel(BaseTopModel):
    xy_windows: Optional[List[XyWindowModel]] = None  # this is dynamically refined to the _XY_PLOT_TYPE's model


class XyTable(DraggableSignalsTable, ContextMenuSignalsTable, HasSaveLoadDataConfig):
    """Mixin into SignalsTable that adds the option to open an XY plot in a separate window."""

    _XY_PLOT_TYPE: Type[BaseXyPlot] = XyPlotSplitter

    @classmethod
    def _create_class_model_bases(cls) -> List[Type[BaseModel]]:
        return [
            create_model(
                "XyTableStateModel",
                __base__=XyTableStateModel,
                xy_windows=(Optional[List[cls._XY_PLOT_TYPE._create_skeleton_model_type()]], None),  # type: ignore
            )
        ]

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._xy_action = QAction("Create X-Y Plot", self)
        self._xy_action.triggered.connect(self._on_create_xy)
        self._xy_plots: List[BaseXyPlot] = []

    def _write_model(self, model: BaseModel) -> None:
        super()._write_model(model)
        assert isinstance(model, XyTableStateModel)
        model.xy_windows = []
        for xy_plot in self._xy_plots:
            model.xy_windows.append(xy_plot._dump_model())  # type: ignore

    def _load_model(self, model: BaseModel) -> None:
        super()._load_model(model)
        assert isinstance(model, XyTableStateModel)
        if model.xy_windows is None:
            return
        for xy_plot in self._xy_plots:  # remove all existing plots
            assert isinstance(xy_plot, QWidget)
            xy_plot.close()
        for xy_window_model in model.xy_windows:  # create plots from model
            xy_plot = self.create_xy()
            xy_plot._load_model(xy_window_model)

    def _populate_context_menu(self, menu: QMenu) -> None:
        super()._populate_context_menu(menu)
        menu.addAction(self._xy_action)

    def _on_create_xy(self) -> Optional[BaseXyPlot]:
        """Creates an XY plot with the selected signal(s) and returns the new plot."""
        data = [self.item(item[0], self.COL_NAME).text() for item in self._ordered_selects]
        if len(data) != 2:
            QMessageBox.critical(
                self, "Error", f"Select two items for X-Y plotting, got {data}", QMessageBox.StandardButton.Ok
            )
            return None
        xy_plot = self.create_xy()
        xy_plot.add_xy(data[0], data[1])
        return xy_plot

    def _make_xy_plots(self) -> BaseXyPlot:
        """Creates the XyPlot widget. self._plots is initialized by this time.
        Optionally override to create a different XyPlotWidget object"""
        return self._XY_PLOT_TYPE(self._plots)

    def create_xy(self) -> BaseXyPlot:
        """Creates and opens an empty XY plot widget."""
        xy_plot = self._make_xy_plots()
        assert isinstance(xy_plot, QWidget)
        xy_plot.show()
        self._xy_plots.append(xy_plot)  # need an active reference to prevent GC'ing
        xy_plot.sigClosed.connect(partial(self._on_closed_xy, xy_plot))
        return xy_plot

    def _on_closed_xy(self, closed: BaseXyPlot) -> None:
        self._xy_plots = [plot for plot in self._xy_plots if plot is not closed]
