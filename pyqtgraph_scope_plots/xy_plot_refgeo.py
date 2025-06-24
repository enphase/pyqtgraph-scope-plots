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
from functools import partial
from typing import Any, List, Tuple, Sequence, Optional, Union, Type

import numpy as np
import numpy.typing as npt
import pyqtgraph as pg
import simpleeval
from PySide6.QtCore import QSignalBlocker, QPointF
from PySide6.QtGui import QAction, QColor, Qt
from PySide6.QtWidgets import QMenu, QColorDialog, QTableWidgetItem
from pydantic import BaseModel, model_validator

from .code_input_dialog import CodeInputDialog
from .signals_table import SignalsTable, HasRegionSignalsTable
from .util import HasSaveLoadConfig
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


class XyRefGeoDrawer:
    """Abstract base class for something that can draw reference geometry.
    This also defines the function name (as an alias for __init__) for simpleeval to bind."""

    @classmethod
    @abstractmethod
    def _fn_name(cls) -> str:
        """Returns the function name to construct this object in simpleeval"""
        ...

    @classmethod
    @abstractmethod
    def _fn_doc(cls) -> str:
        """Returns a short, one-bullet-point documentation for this function, in Qt Markdown"""
        ...

    @abstractmethod
    def _draw(self, color: QColor) -> Sequence[pg.GraphicsObject]:
        """Draws the reference geometry as objects that can be added to the plot"""
        ...


class XyRefGeoVLine(XyRefGeoDrawer):
    def __init__(self, x: float):
        self._x = x

    @classmethod
    def _fn_name(cls) -> str:
        return "axvline"

    @classmethod
    def _fn_doc(cls) -> str:
        return f"""`{cls._fn_name()}(x)`: draws a vertical line"""

    def _draw(self, color: QColor) -> Sequence[pg.GraphicsObject]:
        return [pg.InfiniteLine(pos=(self._x, 0), pen=color)]


class XyRefGeoHLine(XyRefGeoDrawer):
    def __init__(self, y: float):
        self._y = y

    @classmethod
    def _fn_name(cls) -> str:
        return "axhline"

    @classmethod
    def _fn_doc(cls) -> str:
        return f"""`{cls._fn_name()}(y)`: draws a horizontal line"""

    def _draw(self, color: QColor) -> Sequence[pg.GraphicsObject]:
        return [pg.InfiniteLine(pos=(0, self._y), angle=0, pen=color)]


class XyRefGeoBasePoints(XyRefGeoDrawer):
    """Base class that accepts either (xs, ys) or pts, and presents a unified (xs, ys) internal interface"""

    def __init__(
        self,
        *,
        x: Optional[Sequence[float]] = None,
        y: Optional[Sequence[float]] = None,
        pts: Optional[Sequence[Tuple[float, float]]] = None,
    ):
        self._x = x
        self._y = y
        self._pts = pts

    def _get_xy(self) -> Tuple[Sequence[float], Sequence[float]]:
        if self._x is not None and self._y is not None:
            assert self._pts is None, "both xy and pts specified"
            xs = self._x
            ys = self._y
        elif self._pts is not None:
            assert self._x is None and self._y is None, "both xy and pts specified"
            xs = [x for x, y in self._pts]
            ys = [y for x, y in self._pts]
        else:
            raise ValueError("no data specified")
        return xs, ys


class XyRefGeoPolyline(XyRefGeoBasePoints):
    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

    @classmethod
    def _fn_name(cls) -> str:
        return "plot"

    @classmethod
    def _fn_doc(cls) -> str:
        return f"""`{cls._fn_name()}(x=[...], y=[...] | pts=[(x, y), ...])`: draws a polyline through the specified points"""

    def _draw(self, color: QColor) -> Sequence[pg.GraphicsObject]:
        xs, ys = self._get_xy()
        return [pg.PlotCurveItem(x=xs, y=ys, pen=color)]


class XyRefGeoScatter(XyRefGeoBasePoints):
    _MARKER_MAP = {  # map from matplotlib style to pyqtgraph style
        "o": "o",
        "x": "x",
        "+": "+",
        "v": "t",
        "^": "t1",
        "<": "t3",
        ">": "t2",
        "*": "star",
        "D": "d",
        "p": "p",
        "h": "h",  # bestagons
    }

    def __init__(self, *, marker: Union[str, Sequence[str]] = "o", **kwargs: Any):
        super().__init__(**kwargs)
        self._marker = marker

    @classmethod
    def _fn_name(cls) -> str:
        return "scatter"

    @classmethod
    def _fn_doc(cls) -> str:
        return f"""`{cls._fn_name()}(x=[...], y=[...] | pts=[(x, y), ...], [marker='{''.join(cls._MARKER_MAP.keys())}'|[...]])`: draws the specified points"""

    def _draw(self, color: QColor) -> Sequence[pg.GraphicsObject]:
        xs, ys = self._get_xy()
        if isinstance(self._marker, str):
            pg_symbol: Optional[Union[str, List[str]]] = self._MARKER_MAP.get(self._marker)
            assert pg_symbol is not None, f"unknown marker {self._marker}"
        elif isinstance(self._marker, list):
            pg_symbol = []
            for marker_elt in self._marker:
                pg_elt = self._MARKER_MAP.get(marker_elt)
                assert pg_elt is not None, f"unknown marker {marker_elt}"
                pg_symbol.append(pg_elt)
        else:
            raise TypeError("unknown marker type")
        return [pg.ScatterPlotItem(x=xs, y=ys, pen=color, brush=color, symbol=pg_symbol)]


class XyRefGeoText(XyRefGeoDrawer):
    _HORIZONTAL_ALIGN_ANCHOR = {  # map from matplotlib style alignment to pyqtgraph anchor
        "left": 0.0,
        "center": 0.5,
        "right": 1.0,
    }
    _VERTICAL_ALIGN_ANCHOR = {"bottom": 1.0, "center": 0.5, "top": 0.0}

    def __init__(self, x: float, y: float, text: str, *, ha: str = "left", va: str = "bottom"):
        self._x = x
        self._y = y
        self._text = text
        self._ha = ha
        self._va = va

    @classmethod
    def _fn_name(cls) -> str:
        return "text"

    @classmethod
    def _fn_doc(cls) -> str:
        return (
            f"""`{cls._fn_name()}(x, y, text, [ha="{'|'.join(cls._HORIZONTAL_ALIGN_ANCHOR.keys())}"], """
            f"""[va="{'|'.join(cls._VERTICAL_ALIGN_ANCHOR.keys())}"])`: draw text at the specified point"""
        )

    def _draw(self, color: QColor) -> Sequence[pg.GraphicsObject]:
        anchor_x = self._HORIZONTAL_ALIGN_ANCHOR.get(self._ha)
        assert anchor_x is not None, f"unknown ha {self._ha}"
        anchor_y = self._VERTICAL_ALIGN_ANCHOR.get(self._va)
        assert anchor_y is not None, f"unknown va {self._va}"
        text_item = pg.TextItem(text=self._text, color=color, anchor=(anchor_x, anchor_y))
        text_item.setPos(QPointF(self._x, self._y))
        return [text_item]


class RefGeoXyPlotWidget(XyPlotWidget, HasSaveLoadConfig):
    """Mixin into XyPlotWidget that adds support for reference geometry as a polyline.
    For signal purposes, reference geometry is counted as a data item change."""

    _MODEL_BASES = [XyRefGeoModel]

    _REFGEO_CLASSES: List[Type[XyRefGeoDrawer]] = [
        XyRefGeoVLine,
        XyRefGeoHLine,
        XyRefGeoPolyline,
        XyRefGeoScatter,
        XyRefGeoText,
    ]

    _Z_VALUE_REFGEO = -100  # below other geometry

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._refgeo_fns: List[Tuple[str, Any, QColor, bool]] = []  # (expr str, parsed, color, hidden)
        self._refgeo_objs: List[Union[List[pg.GraphicsObject], Exception]] = []  # index-aligned with refgeo_fns

        # copy, since simpleeval internally mutates the functions dict
        simpleeval_fns = {refgeo_class._fn_name(): refgeo_class for refgeo_class in self._REFGEO_CLASSES}
        self._simpleeval = simpleeval.EvalWithCompoundTypes(functions=simpleeval_fns)

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
            prev = ("", None, QColor("darkGray"), False)
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
            [isinstance(objs, Exception) for objs in self._refgeo_objs]
        )  # store last to emit on failing -> ok
        for objs in self._refgeo_objs:
            if not isinstance(objs, Exception):
                for obj in objs:
                    self.removeItem(obj)
        self._refgeo_objs = []
        for expr, parsed, color, hidden in self._refgeo_fns:
            self._simpleeval.names = {
                "data": filtered_data,
            }
            try:
                eval_result = self._simpleeval.eval(expr, parsed)

                if isinstance(eval_result, XyRefGeoDrawer):
                    drawers: Sequence[XyRefGeoDrawer] = [eval_result]
                elif isinstance(eval_result, (list, tuple)):
                    drawers = eval_result
                else:
                    raise TypeError(
                        f"unknown returned type {type(eval_result)}, expected reference geometry object or list of such"
                    )

                drawn_objs: List[pg.GraphicsObject] = []
                for drawer in drawers:
                    assert isinstance(drawer, XyRefGeoDrawer)
                    drawn_objs.extend(drawer._draw(color))

                for obj in drawn_objs:
                    if hidden:
                        obj.hide()
                    obj.setZValue(self._Z_VALUE_REFGEO)
                    self.addItem(obj, ignoreBounds=True)
                self._refgeo_objs.append(drawn_objs)
            except Exception as e:
                self._refgeo_objs.append(e)

        if last_refgeo_err or any([isinstance(objs, Exception) for objs in self._refgeo_objs]):
            self.sigXyDataItemsChanged.emit()

    def hide_refgeo(self, index: int, hidden: bool = True) -> None:
        prev = self._refgeo_fns[index]
        self._refgeo_fns[index] = (prev[0], prev[1], prev[2], hidden)

        objs = self._refgeo_objs[index]
        if not isinstance(objs, Exception):
            for obj in objs:
                if hidden:
                    obj.hide()
                else:
                    obj.show()


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
                if row < len(self._xy_plots._refgeo_objs):
                    objs = self._xy_plots._refgeo_objs[row]
                else:
                    objs = []

                if expr[0] == "#":
                    split = expr.split("\n")
                    name = split[0][1:].lstrip()
                else:
                    name = expr

                if isinstance(objs, Exception):
                    item.setText(f"{objs.__class__.__name__}: {objs}: {name}")
                else:
                    item.setText(f"{name}")

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
        fn_help_str = "\n".join([f"- {refgeo_class._fn_doc()}" for refgeo_class in self._xy_plots._REFGEO_CLASSES])

        err_msg = ""
        while True:
            text, ok = CodeInputDialog.getText(
                self,
                "Add reference geometry",
                "Define reference geometry using the functions below, or a list / tuple of such.  \n"
                "Use `data['...']` to access the data sequence, bounded to the selected region, by name.  \n"
                "Optionally, set the name using a comment on the first line.  \n"
                "Multiple lines of code (nonfunctional line breaks aside) not supported.  \n"
                "These functions are available:  \n" + fn_help_str + err_msg,
                text,
                multiline=True,
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
