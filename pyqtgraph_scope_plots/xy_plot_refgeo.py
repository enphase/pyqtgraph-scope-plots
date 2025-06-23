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
from typing import Any, List, Tuple, Dict, Sequence, Callable, Optional, Union

import numpy as np
import numpy.typing as npt
import simpleeval
from PySide6.QtCore import QSignalBlocker
from PySide6.QtGui import QAction, QColor, Qt
from PySide6.QtWidgets import QMenu, QInputDialog, QLineEdit, QColorDialog, QTableWidgetItem
import pyqtgraph as pg
from pydantic import BaseModel, model_validator

from .code_input_dialog import CodeInputDialog
from .util import HasSaveLoadConfig
from .signals_table import SignalsTable, HasRegionSignalsTable
from .xy_plot import XyPlotWidget, XyPlotTable, ContextMenuXyPlotTable, XyWindowModel, DeleteableXyPlotTable
from .xy_plot_visibility import VisibilityXyPlotTable


class XyRefGeoData(BaseModel):
    expr: str
    hidden: Optional[bool] = None
    color: Optional[str] = None  # QColor name, e.g., '#ffea70' or 'red'


class XyRefGeoModel(XyWindowModel):
    ref_geo: Optional[List[XyRefGeoData]] = None

    @model_validator(mode="before")
    @classmethod
    def _upgrade_schema(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # previously, ref_geo used to be List[str]
            if "ref_geo" in data and len(data["ref_geo"]) > 0 and isinstance(data["ref_geo"][0], str):
                new_ref_geo = []
                for ref_geo_expr in data["ref_geo"]:
                    new_ref_geo.append({"expr": ref_geo_expr})
                data["ref_geo"] = new_ref_geo
        return data


def _refgeo_polyline_fn(*pts: Tuple[float, float]) -> Tuple[Sequence[float], Sequence[float]]:
    """`polyline(*pts: (x, y))`: a polyline from a sequence of `(x, y)` points"""
    return [pt[0] for pt in pts], [pt[1] for pt in pts]


class RefGeoXyPlotWidget(XyPlotWidget, HasSaveLoadConfig):
    """Mixin into XyPlotWidget that adds support for reference geometry as a polyline.
    For signal purposes, reference geometry is counted as a data item change."""

    _MODEL_BASES = [XyRefGeoModel]

    _SIMPLEEVAL_FNS: Dict[str, Callable[[Any], Any]] = {
        "polyline": _refgeo_polyline_fn
    }  # optional additional available in refgeo expressions

    _Z_VALUE_REFGEO = -100  # below other geometry

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._refgeo_fns: List[Tuple[str, Any, QColor, bool]] = []  # (expr str, parsed, color, hidden)
        self._refgeo_curves: List[Union[pg.PlotCurveItem, Exception]] = []  # index-aligned with refgeo_fns

        # copy, since simpleeval internally mutates the functions dict
        self._simpleeval = simpleeval.EvalWithCompoundTypes(functions=self._SIMPLEEVAL_FNS.copy())

    def _write_model(self, model: BaseModel) -> None:
        super()._write_model(model)
        assert isinstance(model, XyRefGeoModel)
        model.ref_geo = [
            XyRefGeoData(expr=expr, color=color.name(), hidden=hidden)
            for expr, parsed, color, hidden in self._refgeo_fns
        ]

    def _load_model(self, model: BaseModel) -> None:
        super()._load_model(model)
        assert isinstance(model, XyRefGeoModel)
        if model.ref_geo is None:
            return

        while len(self._refgeo_fns) > 0:  # delete existing
            self.set_ref_geometry_fn("", 0, update=False)
        for ref_geo in model.ref_geo:
            try:
                color: Optional[QColor] = None
                if ref_geo.color is not None:
                    color = QColor(ref_geo.color)
                self.set_ref_geometry_fn(ref_geo.expr, color=color, hidden=ref_geo.hidden, update=False)
            except Exception as e:
                print(f"failed to restore ref geometry fn {ref_geo.expr}: {e}")  # TODO better logging

    def set_ref_geometry_fn(
        self,
        expr_str: str,
        index: Optional[int] = None,
        *,
        color: Optional[QColor] = None,
        hidden: Optional[bool] = None,
        update: bool = True,
    ) -> None:
        """Sets a reference geometry function at some index. Can raise SyntaxError on a parsing failure.
        If index is None, adds a new function. If valid index and empty string, deletes the function.

        If color / hidden are not specified, keep the previous value (or use a default, if new).

        Optionally set update to false to not fire signals / update to allow a future bulk update"""
        if len(expr_str) == 0:
            if index is not None:
                del self._refgeo_fns[index]
                if update:
                    self._update()
                    self.sigXyDataItemsChanged.emit()
            return
        parsed = self._simpleeval.parse(expr_str)

        if index is not None:
            prev = self._refgeo_fns[index]
        else:
            prev = ("", None, QColor("white"), False)
        new_fns = (expr_str, parsed, color if color is not None else prev[2], hidden if hidden is not None else prev[3])

        if index is not None:
            self._refgeo_fns[index] = new_fns
        else:
            self._refgeo_fns.append(new_fns)

        if update:
            self._update()
            self.sigXyDataItemsChanged.emit()

    def _update(self) -> None:
        super()._update()  # data items drawn here

        region = HasRegionSignalsTable._region_of_plot(self._plots)

        def get_data_region(ts: npt.NDArray[np.float64], ys: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
            """Given ts and xs of a data item, return ys bounded to the input region."""
            ts_lo, ts_hi = HasRegionSignalsTable._indices_of_region(ts, region)
            if ts_lo is None or ts_hi is None:
                return np.array([])
            else:
                return ys[ts_lo:ts_hi]

        filtered_data = {name: get_data_region(ts, ys) for name, (ts, ys) in self._plots._data.items()}

        # draw reference geometry
        last_refgeo_err = any(
            [isinstance(curve, Exception) for curve in self._refgeo_curves]
        )  # store last to emit on failing -> ok
        self._refgeo_curves = []
        for expr, parsed, color, hidden in self._refgeo_fns:
            self._simpleeval.names = {
                "data": filtered_data,
            }
            try:
                xs, ys = self._simpleeval.eval(expr, parsed)
                curve = pg.PlotCurveItem(x=xs, y=ys, name=expr)
                curve.setPen(color=color)
                if hidden:
                    curve.hide()
                curve.setZValue(self._Z_VALUE_REFGEO)
                self.addItem(curve)
                self._refgeo_curves.append(curve)
            except Exception as e:
                self._refgeo_curves.append(e)

        if last_refgeo_err or any([isinstance(curve, Exception) for curve in self._refgeo_curves]):
            self.sigXyDataItemsChanged.emit()

    def hide_refgeo(self, index: int, hidden: bool = True) -> None:
        prev = self._refgeo_fns[index]
        self._refgeo_fns[index] = (prev[0], prev[1], prev[2], hidden)

        curve = self._refgeo_curves[index]
        if isinstance(curve, pg.PlotCurveItem):
            if hidden:
                curve.hide()
            else:
                curve.show()


class RefGeoXyPlotTable(DeleteableXyPlotTable, ContextMenuXyPlotTable, XyPlotTable):
    """Mixin into XyPlotTable that adds support for reference geometry construction"""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._row_offset_refgeo = 0
        self.cellDoubleClicked.connect(self._on_refgeo_double_click)

        self._set_refgeo_color_action = QAction("Set reference geometry color", self)
        self._set_refgeo_color_action.triggered.connect(self._on_set_refgeo_color)
        self.itemChanged.connect(self._on_refgeo_visibility_toggle)

    def _populate_context_menu(self, menu: QMenu) -> None:
        """Called when the context menu is created, to populate its items."""
        super()._populate_context_menu(menu)
        add_refgeo = QAction("Add reference geometry", self)
        add_refgeo.triggered.connect(partial(self._on_set_refgeo, None))
        menu.addAction(add_refgeo)
        refgeo_rows = [item.row() >= self._row_offset_refgeo for item in self.selectedItems()]
        if any(refgeo_rows):
            self._set_refgeo_color_action.setEnabled(True)
        else:
            self._set_refgeo_color_action.setEnabled(False)
        menu.addAction(self._set_refgeo_color_action)

    def _update(self) -> None:
        super()._update()
        assert isinstance(self._xy_plots, RefGeoXyPlotWidget)
        self._row_offset_refgeo = self.rowCount()
        self.setRowCount(self._row_offset_refgeo + len(self._xy_plots._refgeo_fns))
        with QSignalBlocker(self):  # prevent hidden state from modifying hidden state
            for row, (expr, _, color, hidden) in enumerate(self._xy_plots._refgeo_fns):
                table_row = self._row_offset_refgeo + row
                item = SignalsTable._create_noneditable_table_item()
                curve = self._xy_plots._refgeo_curves[row]
                if isinstance(curve, Exception):
                    item.setText(f"{expr}: {curve.__class__.__name__}: {curve}")
                else:
                    item.setText(expr)
                item.setForeground(color)
                self.setItem(table_row, self.COL_X_NAME, item)
                self.setSpan(table_row, self.COL_X_NAME, 1, 2)

                if isinstance(self, VisibilityXyPlotTable):
                    item = SignalsTable._create_noneditable_table_item()
                    item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                    if hidden:
                        item.setCheckState(Qt.CheckState.Unchecked)
                    else:
                        item.setCheckState(Qt.CheckState.Checked)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.setItem(table_row, self.COL_VISIBILITY, item)

    def _on_refgeo_double_click(self, row: int, col: int) -> None:
        if row >= self._row_offset_refgeo and col == self.COL_X_NAME:
            self._on_set_refgeo(row - self._row_offset_refgeo)

    def _on_set_refgeo(self, index: Optional[int] = None) -> None:
        assert isinstance(self._xy_plots, RefGeoXyPlotWidget)
        text = ""
        if index is not None:
            text = self._xy_plots._refgeo_fns[index][0]
        fn_help_str = "\n".join([f"- {fn.__doc__}" for fn_name, fn in self._xy_plots._SIMPLEEVAL_FNS.items()])

        err_msg = ""
        while True:
            text, ok = CodeInputDialog.getText(
                self,
                "Add reference geometry",
                "Function for reference geometry, using the helper functions below.  \n"
                "Use `data['...']` to access the data sequence, bounded to the selected region, by name.  \n"
                "These helper functions are available:  \n" + fn_help_str + err_msg,
                text,
            )
            if not ok:
                return

            try:
                self._xy_plots.set_ref_geometry_fn(text, index)
                return
            except SyntaxError as exc:
                err_msg = f"""\n\n<br/>`{exc.__class__.__name__}: {exc}`"""

    def _rows_deleted_event(self, rows: List[int]) -> None:
        for row in reversed(sorted(rows)):
            if row >= self._row_offset_refgeo:
                self._xy_plots.set_ref_geometry_fn("", row - self._row_offset_refgeo)
        super()._rows_deleted_event(rows)

    def _on_set_refgeo_color(self) -> None:
        assert isinstance(self._xy_plots, RefGeoXyPlotWidget)
        color = QColorDialog.getColor()
        for row in set([item.row() for item in self.selectedItems()]):
            refgeo_row = row - self._row_offset_refgeo
            if refgeo_row >= 0:
                orig_expr = self._xy_plots._refgeo_fns[refgeo_row][0]
                self._xy_plots.set_ref_geometry_fn(orig_expr, refgeo_row, color=color)

    def _on_refgeo_visibility_toggle(self, item: QTableWidgetItem) -> None:
        refgeo_row = item.row() - self._row_offset_refgeo
        if not isinstance(self, VisibilityXyPlotTable):
            return
        if item.column() != self.COL_VISIBILITY or refgeo_row < 0:
            return
        assert isinstance(self._xy_plots, RefGeoXyPlotWidget)
        self._xy_plots.hide_refgeo(refgeo_row, item.checkState() == Qt.CheckState.Unchecked)
