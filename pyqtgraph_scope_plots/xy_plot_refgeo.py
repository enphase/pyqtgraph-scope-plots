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
from typing import Any, List, Tuple, Dict, Sequence, Callable

import simpleeval
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QInputDialog, QLineEdit
import pyqtgraph as pg

from .signals_table import SignalsTable
from .xy_plot import XyPlotWidget, XyPlotTable, ContextMenuXyPlotTable


def _refgeo_polyline_fn(*pts: Tuple[float, float]) -> Tuple[Sequence[float], Sequence[float]]:
    """polyline(*pts: (x, y)) -> (xs, ys): turns of sequence of (x, y) points into (xs, ys)"""
    return [pt[0] for pt in pts], [pt[1] for pt in pts]


class RefGeoXyPlotWidget(XyPlotWidget):
    """Mixin into XyPlotWidget that adds support for reference geometry as a polyline.
    For signal purposes, reference geometry is counted as a data item change."""

    _SIMPLEEVAL_FNS: Dict[str, Callable[[Any], Any]] = {
        "polyline": _refgeo_polyline_fn
    }  # optional additional available in refgeo expressions

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._refgeo_fns: List[Tuple[str, Any]] = []  # (expr str, parsed)
        # copy, since simpleeval internally mutates the functions dict
        self._simpleeval = simpleeval.EvalWithCompoundTypes(functions=self._SIMPLEEVAL_FNS.copy())

    def add_ref_geometry_fn(self, expr_str: str) -> None:
        """Adds a reference geometry function. Can raise SyntaxError on a parsing failure."""
        if len(expr_str) == 0:
            return
        parsed = self._simpleeval.parse(expr_str)
        self._refgeo_fns.append((expr_str, parsed))
        self._update()
        self.sigXyDataItemsChanged.emit()

    def _update(self) -> None:
        super()._update()  # data items drawn here

        # draw reference geometry
        for refgeo_expr, refgeo_parsed in self._refgeo_fns:
            self._simpleeval.names = {
                # "data": other_data_dict,  # TODO support aligned data
            }
            try:
                xs, ys = self._simpleeval.eval(refgeo_expr, refgeo_parsed)
                curve = pg.PlotCurveItem(x=xs, y=ys)
                self.addItem(curve)
            except Exception as e:
                pass  # TODO save somewhere and fire a signal


class RefGeoXyPlotTable(ContextMenuXyPlotTable, XyPlotTable):
    """Mixin into XyPlotTable that adds support for reference geometry construction"""

    def _populate_context_menu(self, menu: QMenu) -> None:
        """Called when the context menu is created, to populate its items."""
        super()._populate_context_menu(menu)
        add_refgeo = QAction("Add reference geometry", self)
        add_refgeo.triggered.connect(self._on_add_refgeo)
        menu.addAction(add_refgeo)

    def _update(self) -> None:
        super()._update()
        assert isinstance(self._xy_plots, RefGeoXyPlotWidget)
        offset = self.rowCount()
        self.setRowCount(offset + len(self._xy_plots._refgeo_fns))
        for row, (refgeo_expr, _) in enumerate(self._xy_plots._refgeo_fns):
            item = SignalsTable._create_noneditable_table_item()
            item.setText(refgeo_expr)
            self.setItem(offset + row, self.COL_X_NAME, item)
            self.setSpan(offset + row, self.COL_X_NAME, 1, 2)

    def _on_add_refgeo(self) -> None:
        assert isinstance(self._xy_plots, RefGeoXyPlotWidget)
        text = ""
        err_msg = ""
        fn_help_str = "\n".join([f"- {fn.__doc__}" for fn_name, fn in self._xy_plots._SIMPLEEVAL_FNS.items()])
        while True:
            text, ok = QInputDialog().getText(
                self,
                "Add reference geometry",
                "Function for reference geometry, as a tuple of xs, ys, for example '([0, 1], [0, 1])' for a diagonal line. \n"
                "Use 'data['...']' or 'data.get('...') to access the data sequence (bounded to the selected region) by name. \n"
                "These helper functions are available: \n" + fn_help_str + err_msg,
                QLineEdit.EchoMode.Normal,
                text,
            )
            if not ok:
                return
            else:
                try:
                    self._xy_plots.add_ref_geometry_fn(text)
                    return
                except SyntaxError as e:
                    err_msg = f"\n\n{e.__class__.__name__}: {e}"
