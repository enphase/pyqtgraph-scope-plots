from typing import Any, Optional
import pyqtgraph as pg
from pydantic import BaseModel

from pyqtgraph_scope_plots import MultiPlotWidget, HasSaveLoadDataConfig


class ShowLegendsStateModel(BaseModel):
    show_legends: Optional[bool] = None


class LegendPlotWidget(MultiPlotWidget, HasSaveLoadDataConfig):
    """Adds a show-legend API. Once the legend is shown, it cannot be hidden again, since pyqtgraph
    does not provide those APIs"""

    _MODEL_BASES = [ShowLegendsStateModel]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._show_legend: bool = False
        super().__init__(*args, **kwargs)

    def _write_model(self, model: BaseModel) -> None:
        super()._write_model(model)
        assert isinstance(model, ShowLegendsStateModel)
        model.show_legends = self._show_legend

    def _load_model(self, model: BaseModel) -> None:
        super()._load_model(model)
        assert isinstance(model, ShowLegendsStateModel)
        if model.show_legends == True and not self._show_legend:
            self.show_legends()

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
