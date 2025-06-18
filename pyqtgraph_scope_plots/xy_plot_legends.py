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
from typing import Any, cast

import pyqtgraph as pg
from pydantic import BaseModel

from .util import HasSaveLoadDataConfig
from .legend_plot_widget import ShowLegendsStateModel
from .xy_plot_table import XyTable
from .xy_plot import BaseXyPlot


class XyTableLegends(XyTable, HasSaveLoadDataConfig):
    """Mixin into XyTable that allows legends to be shown."""

    _MODEL_BASES = [ShowLegendsStateModel]

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._show_legend: bool = False

    def _write_model(self, model: BaseModel) -> None:
        super()._write_model(model)
        assert isinstance(model, ShowLegendsStateModel)
        model.show_legends = self._show_legend

    def _load_model(self, model: BaseModel) -> None:
        super()._load_model(model)
        assert isinstance(model, ShowLegendsStateModel)
        if model.show_legends == True and not self._show_legend:
            self.show_legends()

    def show_legends(self) -> None:
        self._show_legend = True
        for xy_plot in self._xy_plots:
            cast(pg.PlotItem, xy_plot.get_plot_widget().getPlotItem()).addLegend()
            xy_plot.get_plot_widget()._update()

    def create_xy(self) -> BaseXyPlot:
        xy_plot = super().create_xy()
        if self._show_legend:
            cast(pg.PlotItem, xy_plot.get_plot_widget().getPlotItem()).addLegend()
        return xy_plot
