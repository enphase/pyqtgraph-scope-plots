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
from abc import abstractmethod
from typing import Any, Optional
import pyqtgraph as pg
from pydantic import BaseModel

from .util import HasSaveLoadDataConfig
from .multi_plot_widget import MultiPlotWidget


class ShowLegendsStateModel(BaseModel):
    show_legends: Optional[bool] = None


class BaseLegendSaveLoad(HasSaveLoadDataConfig):
    _MODEL_BASES = [ShowLegendsStateModel]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._show_legend: bool = False  # inspect this to show legend on plot creation
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

    @abstractmethod
    def show_legends(self) -> None:
        """Implement me to show legends in response to some action"""
        ...


class LegendPlotWidget(BaseLegendSaveLoad, MultiPlotWidget):
    """Adds a show-legend API. Once the legend is shown, it cannot be hidden again, since pyqtgraph
    does not provide those APIs"""

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
