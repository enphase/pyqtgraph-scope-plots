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
from typing import cast

import pyqtgraph as pg

from .legend_plot_widget import BaseLegendSaveLoad
from .xy_plot import BaseXyPlot
from .xy_plot_table import XyTable


class XyTableLegends(BaseLegendSaveLoad, XyTable):
    """Mixin into XyTable that allows legends to be shown."""

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
