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

import numbers
from typing import Dict, Tuple, List, Any, Mapping, Union

import numpy as np
import numpy.typing as npt
import simpleeval
from PySide6.QtGui import QColor, QAction
from PySide6.QtWidgets import QTableWidgetItem, QMenu, QInputDialog, QLineEdit

from .cache_dict import IdentityCacheDict
from .signals_table import ContextMenuSignalsTable
from .util import not_none


class TransformsSignalsTable(ContextMenuSignalsTable):
    """Mixin into SignalsTable that adds a UI for the user to specify a transform using a subset of Python code.
    This parses the user input and provides a get_transform."""

    COL_TRANSFORM = -1

    class AllDataDict:
        """Takes in multiple series of (xs, ys) and returns the value at exactly the current x.
        Mimicks the behavior of a dict that contains all the y values, but more efficient since it doesn't
        do the indexing calculation until a value is requested.
        Requires x to be monotonically increasing. Optimized for the case where gets are done on almost every element,
        but robust to sequences that have wildly different xs."""

        def __init__(
            self,
            data: Mapping[str, Tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]],
        ):
            self._x = float("NaN")
            self._data = data
            self._data_indices: Dict[str, int] = {}  # last index at the data name

        def _set_x(self, x: float) -> None:
            """Updates the x value for the next get"""
            self._x = x

        def __getitem__(self, key: str) -> Any:
            elt = self.get(key)
            if elt is None:
                raise KeyError
            else:
                return elt

        def get(self, key: str, default: Any = None) -> Any:
            xs, ys = self._data[key]
            while True:
                prev_index = self._data_indices.get(key, 0)
                if prev_index >= len(xs):  # exceeded length of array
                    return default
                elif xs[prev_index] == self._x:
                    return ys[prev_index]
                elif xs[prev_index] > self._x:  # past the x being searched for
                    return default
                else:  # before the x being searched for, advance to the next elt
                    self._data_indices[key] = prev_index + 1

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._set_transform_action = QAction("Set Function", self)
        self._set_transform_action.triggered.connect(self._on_set_transform)
        self.cellDoubleClicked.connect(self._on_transform_double_click)

        self._transforms: Dict[str, Tuple[str, Any]] = {}  # (expr str, parsed)
        self._simpleeval = simpleeval.SimpleEval()
        self._cached_results = IdentityCacheDict[
            npt.NDArray[np.float64], npt.NDArray[np.float64]
        ]()  # src data -> output data

    def apply_transform(
        self,
        data_name: str,
        all_data: Mapping[str, Tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]],
    ) -> Union[npt.NDArray[np.float64], Exception]:
        """Applies a transform to the specified data_name and data, using self._table.transform.
        Returns the transformed data, which may be the input data if no transform is specified.
        """
        xs, ys = all_data[data_name]
        transform = self._transforms.get(data_name)
        if not transform:
            return ys
        expr, parsed = transform

        input_all_data_refs = [elt for arrs in all_data.values() for elt in arrs]
        cached_result = self._cached_results.get(ys, expr, input_all_data_refs)
        if cached_result is not None:
            return cached_result

        other_data_dict = self.AllDataDict(all_data)
        new_ys = []
        for x, y in zip(xs, ys):
            try:
                other_data_dict._set_x(x)
                self._simpleeval.names = {
                    "x": y,
                    "t": x,
                    "data": other_data_dict,
                }
                new_y = self._simpleeval.eval(expr, parsed)
                # note, float and int are technically different, but are same enough here
                if not (isinstance(new_y, numbers.Number) and isinstance(y, numbers.Number)) and type(new_y) != type(y):
                    raise TypeError
                new_ys.append(new_y)
            except Exception as e:
                data_name_to_row = {data_name: i for i, data_name in enumerate(self._data_items.keys())}
                exc_text = f"at ({x}, {y}): {e.__class__.__name__}: {e}"
                not_none(self.item(data_name_to_row[data_name], self.COL_TRANSFORM)).setText(exc_text)
                not_none(self.item(data_name_to_row[data_name], self.COL_TRANSFORM)).setToolTip(exc_text)
                return e
        result = np.array(new_ys)
        result.flags.writeable = ys.flags.writeable
        self._cached_results.set(ys, expr, input_all_data_refs, result)
        return result

    def _post_cols(self) -> int:
        self.COL_TRANSFORM = super()._post_cols()
        return self.COL_TRANSFORM + 1

    def _init_table(self) -> None:
        super()._init_table()
        self.setHorizontalHeaderItem(self.COL_TRANSFORM, QTableWidgetItem("Function"))

    def _populate_context_menu(self, menu: QMenu) -> None:
        super()._populate_context_menu(menu)
        menu.addAction(self._set_transform_action)

    def _on_transform_double_click(self, row: int, col: int) -> None:
        if col == self.COL_TRANSFORM:
            self._on_set_transform()

    def _on_set_transform(self) -> None:
        data_names = list(self._data_items.keys())
        selected_data_names = [data_names[item.row()] for item in self.selectedItems()]
        text = ""
        for data_name in selected_data_names:  # collect the first previously-specified transform
            prev_str = self._transforms.get(data_name, (None, None))[0]
            if prev_str is not None and not text:
                text = prev_str

        err_msg = ""
        while True:
            text, ok = QInputDialog().getText(
                self,
                f"Function for {', '.join(selected_data_names)}",
                "Function code, use 'x' for current value, 't' for the timestamp, and\n"
                "'data['...']' or 'data.get('...')' to access other data at the same timestamp" + err_msg,
                QLineEdit.EchoMode.Normal,
                text,
            )
            if not ok:
                return
            if not text:
                parsed = None
                break
            else:
                try:
                    parsed = self._simpleeval.parse(text)
                    break
                except SyntaxError as e:
                    err_msg = f"\n\n{e.__class__.__name__}: {e}"

        for data_name in selected_data_names:
            if not text:
                if data_name in self._transforms:
                    del self._transforms[data_name]
            else:
                self._transforms[data_name] = (text, parsed)
        for item in self.selectedItems():
            not_none(self.item(item.row(), self.COL_TRANSFORM)).setText(text)
            not_none(self.item(item.row(), self.COL_TRANSFORM)).setToolTip(text)
        self.sigTransformChanged.emit(selected_data_names)

    def set_data_items(self, new_data_items: List[Tuple[str, QColor]]) -> None:
        super().set_data_items(new_data_items)
        for row, (name, color) in enumerate(self._data_items.items()):
            transform = self._transforms.get(name)
            if transform is not None:
                not_none(self.item(row, self.COL_TRANSFORM)).setText(transform[0])
                not_none(self.item(row, self.COL_TRANSFORM)).setToolTip(transform[0])
            else:
                not_none(self.item(row, self.COL_TRANSFORM)).setText("")
                not_none(self.item(row, self.COL_TRANSFORM)).setToolTip("")
