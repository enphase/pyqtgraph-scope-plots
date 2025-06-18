from typing import Any
import pyqtgraph as pg

from pyqtgraph_scope_plots import MultiPlotWidget


class LegendPlotWidget(MultiPlotWidget):
    """Adds a show-legend API. Once the legend is shown, it cannot be hidden again, since pyqtgraph
    does not provide those APIs"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._show_legend: bool = False
        super().__init__(*args, **kwargs)

    def _init_plot_item(self, plot_item: pg.PlotItem) -> pg.PlotItem:
        plot_item = super()._init_plot_item(plot_item)
        if self._show_legend:
            plot_item.addLegend()
        return plot_item

    def show_legends(self) -> None:
        self._show_legend = True
        for plot_item, _ in self._plot_item_data.items():
            plot_item.addLegend()
        self._update_plots()
