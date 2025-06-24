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
from typing import Dict, Tuple, List, Any, Mapping, Union, Optional

import numpy as np
import numpy.typing as npt
import simpleeval
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QTableWidgetItem, QMenu
from pydantic import BaseModel

from .code_input_dialog import CodeInputDialog
from .multi_plot_widget import MultiPlotWidget
from .signals_table import ContextMenuSignalsTable
from .util import IdentityCacheDict, DataTopModel, HasSaveLoadDataConfig, BaseTopModel, not_none


class TransformsDataStateModel(DataTopModel):
    transform: Optional[str] = None


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


class TransformsPlotWidget(MultiPlotWidget, HasSaveLoadDataConfig):
    """MultiPlotWidget that adds a user-defined data transform."""

    _DATA_MODEL_BASES = [TransformsDataStateModel]

    def __init__(self, *args: Any, **kwargs: Any):
        self._simpleeval = simpleeval.SimpleEval()

        self._transforms: Dict[str, Tuple[str, Any]] = {}  # (expr str, parsed)
        self._transforms_errs: Dict[str, Optional[Exception]] = {}
        self._transforms_cached_results = IdentityCacheDict[
            npt.NDArray[np.float64], npt.NDArray[np.float64]
        ]()  # src data -> output data

        super().__init__(*args, **kwargs)

    def _write_model(self, model: BaseModel) -> None:
        super()._write_model(model)
        assert isinstance(model, BaseTopModel)
        for data_name, data_model in model.data.items():
            assert isinstance(data_model, TransformsDataStateModel)
            transform, _ = self._transforms.get(data_name, ("", None))
            data_model.transform = transform

    def _load_model(self, model: BaseModel) -> None:
        super()._load_model(model)
        assert isinstance(model, BaseTopModel)
        for data_name, data_model in model.data.items():
            assert isinstance(data_model, TransformsDataStateModel)
            if data_model.transform is not None:
                try:
                    self.set_transform([data_name], data_model.transform, update=False)
                except Exception as e:
                    print(f"failed to restore transform fn {data_model.transform}: {e}")  # TODO better logging

    def _apply_transform(
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
        cached_result = self._transforms_cached_results.get(ys, expr, input_all_data_refs)
        if cached_result is not None:
            return cached_result

        other_data_dict = AllDataDict(all_data)
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
                    raise TypeError(f"returned {new_y} of type {type(new_y)} != original type {type(y)}")
                new_ys.append(new_y)
            except Exception as e:
                return e
        result = np.array(new_ys)
        result.flags.writeable = ys.flags.writeable
        self._transforms_cached_results.set(ys, expr, input_all_data_refs, result)
        return result

    def _transform_data(
        self, data: Mapping[str, Tuple[npt.NDArray, npt.NDArray]]
    ) -> Mapping[str, Tuple[npt.NDArray, npt.NDArray]]:
        data = super()._transform_data(data)
        transformed_data = {}
        last_transform_errs = self._transforms_errs
        for data_name in data.keys():
            transformed = self._apply_transform(data_name, data)
            if isinstance(transformed, Exception):
                self._transforms_errs[data_name] = transformed
                continue
            else:
                if data_name in self._transforms_errs:
                    del self._transforms_errs[data_name]
            transformed_data[data_name] = data[data_name][0], transformed
        if len(last_transform_errs) > 0 or len(self._transforms_errs) > 0:
            self.sigDataUpdated.emit()  # error counts as a transform update
        return transformed_data

    def set_transform(self, data_names: List[str], transform_expr: str, update: bool = True) -> None:
        """Sets the transform on a particular data and applies it.
        Raises SyntaxError (from simpleeval) on a parsing failure. Does not do any other processing / checks.
        Optionally, updating can be disabled for performance, for example to batch-update after a bunch of ops."""
        if len(transform_expr) > 0:
            parsed = self._simpleeval.parse(transform_expr)
        else:
            parsed = None

        for data_name in data_names:
            if parsed is None:
                if data_name in self._transforms:
                    del self._transforms[data_name]
            else:
                self._transforms[data_name] = (transform_expr, parsed)

        if update:
            self._update_plots()
            self.sigDataUpdated.emit()


class TransformsSignalsTable(ContextMenuSignalsTable):
    """Mixin into SignalsTable that adds a UI for the user to specify a transform using a subset of Python code.
    Only provides UI items into the APIs in TransformsPlotWidget"""

    COL_TRANSFORM = -1

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        assert isinstance(self._plots, TransformsPlotWidget)

        self._set_transform_action = QAction("Set Function", self)
        self._set_transform_action.triggered.connect(self._on_set_transform)
        self.cellDoubleClicked.connect(self._on_transform_double_click)
        self._plots.sigDataUpdated.connect(self._update_transforms)

    def _post_cols(self) -> int:
        self.COL_TRANSFORM = super()._post_cols()
        return self.COL_TRANSFORM + 1

    def _init_table(self) -> None:
        super()._init_table()
        self.setHorizontalHeaderItem(self.COL_TRANSFORM, QTableWidgetItem("Function"))

    def _update(self) -> None:
        super()._update()
        self._update_transforms()

    def _update_transforms(self) -> None:
        assert isinstance(self._plots, TransformsPlotWidget)

        for row, (name, color) in enumerate(self._data_items.items()):
            expr_str, _ = self._plots._transforms.get(name, ("", None))
            exc_opt = self._plots._transforms_errs.get(name, None)
            if exc_opt is not None:
                expr_str = f"{expr_str}: {exc_opt.__class__.__name__}: {exc_opt}"

            not_none(self.item(row, self.COL_TRANSFORM)).setText(expr_str)
            not_none(self.item(row, self.COL_TRANSFORM)).setToolTip(expr_str)

    def _populate_context_menu(self, menu: QMenu) -> None:
        super()._populate_context_menu(menu)
        menu.addAction(self._set_transform_action)

    def _on_transform_double_click(self, row: int, col: int) -> None:
        if col == self.COL_TRANSFORM:
            self._on_set_transform()

    def _on_set_transform(self) -> None:
        assert isinstance(self._plots, TransformsPlotWidget)
        data_names = list(self._plots._data_items.keys())
        selected_data_names = [data_names[item.row()] for item in self.selectedItems()]
        text = ""
        for data_name in selected_data_names:  # collect the first previously-specified transform
            prev_str, _ = self._plots._transforms.get(data_name, (None, None))
            if prev_str is not None and not text:
                text = prev_str

        err_msg = ""
        while True:
            text, ok = CodeInputDialog.getText(
                self,
                f"Function for {', '.join(selected_data_names)}",
                "Function code, use `x` for current value, `t` for the timestamp, and  \n  "
                "`data['...']` or `data.get('...')` to access other data at the same timestamp" + err_msg,
                text,
            )
            if not ok:
                return

            try:
                self._plots.set_transform(selected_data_names, text)
                return
            except SyntaxError as exc:
                err_msg = f"""\n\n<br/>`{exc.__class__.__name__}: {exc}`"""
