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
from typing import Any, List, Tuple, Dict, Sequence

import simpleeval
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu
import pyqtgraph as pg

from .xy_plot import XyPlotWidget, XyPlotTable, ContextMenuXyPlotTable


def _refgeo_polyline_fn(*pts: Tuple[float, float]) -> Tuple[Sequence[float], Sequence[float]]:
    return [pt[0] for pt in pts], [pt[1] for pt in pts]


class RefGeoXyPlotWidget(XyPlotWidget):
    """Mixin into XyPlotWidget that adds support for reference geometry as a polyline."""

    _SIMPLEEVAL_FNS: Dict[str, Any] = {
        "polyline": _refgeo_polyline_fn
    }  # optional additional available in refgeo expressions

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._ref_geometry_fns: List[Tuple[str, Any]] = []  # (expr str, parsed)
        self._simpleeval = simpleeval.EvalWithCompoundTypes(functions=self._SIMPLEEVAL_FNS)

    def add_ref_geometry_fn(self, expr_str: str) -> None:
        """Adds a reference geometry function. Can raise SyntaxError on a parsing failure."""
        if len(expr_str) == 0:
            return
        parsed = self._simpleeval.parse(expr_str)
        self._ref_geometry_fns.append((expr_str, parsed))
        self._update()

    def _update(self) -> None:
        super()._update()  # data items drawn here

        # draw reference geometry
        for refgeo_expr, refgeo_parsed in self._ref_geometry_fns:
            self._simpleeval.names = {
                # "data": other_data_dict,  # TODO support aligned data
            }

            xs, ys = self._simpleeval.eval(refgeo_expr, refgeo_parsed)
            curve = pg.PlotCurveItem(x=xs, y=ys)
            self.addItem(curve)


class RefGeoXyPlotTable(ContextMenuXyPlotTable, XyPlotTable):
    """Mixin into XyPlotTable that adds support for reference geometry construction"""

    def _populate_context_menu(self, menu: QMenu) -> None:
        """Called when the context menu is created, to populate its items."""
        super()._populate_context_menu(menu)
        add_refgeo = QAction("Add reference geometry", self)
        add_refgeo.triggered.connect(self._on_add_refgeo)
        menu.addAction(add_refgeo)

    def _on_add_refgeo(self) -> None:
        raise NotImplementedError  # TODO IMPLEMENT ME
