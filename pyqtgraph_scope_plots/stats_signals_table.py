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

import math
import time
import weakref
from typing import Dict, Tuple, List, Any, Optional

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import Signal, QThread, QMutex, QMutexLocker, QThreadPool, QRunnable, QObject, Qt
from PySide6.QtWidgets import QTableWidgetItem
from pydantic import BaseModel

from .signals_table import HasRegionSignalsTable
from .util import IdentityCacheDict, HasSaveLoadDataConfig, not_none


class StatsTableStateModel(BaseModel):
    stats_disabled: Optional[bool] = None


class StatsSignalsTable(HasRegionSignalsTable, HasSaveLoadDataConfig):
    """Mixin into SignalsTable with statistics rows. Optional range to specify computation of statistics.
    Values passed into set_data must all be numeric."""

    COL_STAT = -1
    COL_STAT_MIN = 0  # offset from COL_STAT
    COL_STAT_MAX = 1
    COL_STAT_AVG = 2
    COL_STAT_RMS = 3
    COL_STAT_STDEV = 4
    STATS_COLS = [
        COL_STAT_MIN,
        COL_STAT_MAX,
        COL_STAT_AVG,
        COL_STAT_RMS,
        COL_STAT_STDEV,
    ]

    _MODEL_BASES = [StatsTableStateModel]

    _FULL_RANGE = (-float("inf"), float("inf"))

    class StatsCalculatorSignals(QObject):
        # signals don't work with mixins, so this is in its own object
        update = Signal(object, object, object)  # input array, region, {stat (by offset col) -> value}

    class StatsCalculatorWorker(QRunnable):
        """Stats calculated in a separate thread to avoid blocking the main GUI thread when large regions
        are selected. The thread is persistent.
        This uses shared state variable to communicate the next computation task with a request signal to
        wake up the thread. Earlier, unserviced requests are clobbered."""

        def __init__(self, parent: "StatsSignalsTable") -> None:
            super().__init__()
            self._parent = parent

        def run(self) -> None:
            """Processes the current request, if it is new."""
            while True:  # wait for debounce target to stabilize
                with QMutexLocker(self._parent._request_mutex):
                    debounce_target_ns = self._parent._debounce_target_ns
                delay_time_ns = debounce_target_ns - time.time_ns()
                if delay_time_ns > 0:
                    QThread.msleep(delay_time_ns // 1000000)
                else:
                    break

            with QMutexLocker(self._parent._request_mutex):
                request_data = self._parent._request_data
                request_region = self._parent._request_region
                if request_data is self._parent._last_data and request_region == self._parent._last_region:
                    return
                self._parent._last_data = request_data
                self._parent._last_region = request_region

            for xs_ys_ref in request_data:
                if self._parent._stats_calculation_disabled:  # terminate if disabled
                    return
                with QMutexLocker(self._parent._request_mutex):
                    if self._parent._debounce_target_ns != debounce_target_ns:
                        return

                xs = xs_ys_ref[0]()
                ys = xs_ys_ref[1]()
                if xs is None or ys is None:  # skip objects that have been deleted
                    continue
                low_index, high_index = HasRegionSignalsTable._indices_of_region(xs, request_region)
                if low_index is None or high_index is None:  # empty set
                    ys_region = np.array([])
                else:
                    ys_region = ys[low_index:high_index]
                stats_dict = self._calculate_stats(ys_region)
                self._parent._stats_signals.update.emit(ys, request_region, stats_dict)
                QThread.msleep(1)  # yield the thread to ensure this is low priority

        @classmethod
        def _calculate_stats(cls, ys: npt.NDArray[np.float64]) -> Dict[int, float]:
            """Calculates stats (as dict of col offset -> value) for the specified xs, ys.
            Does not spawn a separate thread, does not affect global state."""
            if len(ys) == 0:
                return {}
            stats_dict = {}
            mean = sum(ys) / len(ys)
            stats_dict[StatsSignalsTable.COL_STAT_MIN] = min(ys)
            stats_dict[StatsSignalsTable.COL_STAT_MAX] = max(ys)
            stats_dict[StatsSignalsTable.COL_STAT_AVG] = mean
            stats_dict[StatsSignalsTable.COL_STAT_RMS] = math.sqrt(sum([x**2 for x in ys]) / len(ys))
            stats_dict[StatsSignalsTable.COL_STAT_STDEV] = math.sqrt(sum([(x - mean) ** 2 for x in ys]) / len(ys))
            return stats_dict

    def _post_cols(self) -> int:
        self.COL_STAT = super()._post_cols()
        return self.COL_STAT + 5

    def _init_table(self) -> None:
        super()._init_table()
        self.setHorizontalHeaderItem(self.COL_STAT + self.COL_STAT_MIN, QTableWidgetItem("Min"))
        self.setHorizontalHeaderItem(self.COL_STAT + self.COL_STAT_MAX, QTableWidgetItem("Max"))
        self.setHorizontalHeaderItem(self.COL_STAT + self.COL_STAT_AVG, QTableWidgetItem("Avg"))
        self.setHorizontalHeaderItem(self.COL_STAT + self.COL_STAT_RMS, QTableWidgetItem("RMS"))
        self.setHorizontalHeaderItem(self.COL_STAT + self.COL_STAT_STDEV, QTableWidgetItem("StDev"))

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._stats_calculation_disabled = False

        super().__init__(*args, **kwargs)
        # since calculating stats across the full range is VERY EXPENSIVE, cache the results
        self._full_range_stats = IdentityCacheDict[npt.NDArray[np.float64], Dict[int, float]]()  # array -> stats dict
        self._region_stats = IdentityCacheDict[npt.NDArray[np.float64], Dict[int, float]]()  # array -> stats dict

        self._plots.sigDataUpdated.connect(lambda: self._update_stats_task(0, False))
        self._plots.sigCursorRangeChanged.connect(lambda: self._update_stats_task(100, True))

        # shared state for current stats request
        self._request_mutex = QMutex()
        self._request_data: List[Tuple[weakref.ref[npt.NDArray[np.float64]], weakref.ref[npt.NDArray[np.float64]]]] = []
        self._last_data = self._request_data
        self._request_region: Tuple[float, float] = StatsSignalsTable._FULL_RANGE
        self._last_region = self._request_region
        self._debounce_target_ns: int = 0  # earliest time to execute this task, for debouncing

        # stats threading
        self._stats_threadpool = QThreadPool()
        self._stats_threadpool.setMaxThreadCount(1)
        self._stats_threadpool.setThreadPriority(QThread.Priority.LowestPriority)
        self._stats_signals = self.StatsCalculatorSignals()
        self._stats_signals.update.connect(self._on_stats_updated)

    def _update(self) -> None:
        super()._update()
        self._update_stats_disabled()

    def _write_model(self, model: BaseModel) -> None:
        assert isinstance(model, StatsTableStateModel)
        super()._write_model(model)
        model.stats_disabled = self._stats_calculation_disabled

    def _load_model(self, model: BaseModel) -> None:
        assert isinstance(model, StatsTableStateModel)
        super()._load_model(model)
        if model.stats_disabled is not None:
            self.disable_stats(model.stats_disabled)

    def stats_disabled(self) -> bool:
        """Returns whether stats calculation is disabled."""
        return self._stats_calculation_disabled

    def disable_stats(self, disable: bool = True) -> None:
        """Call this to disable stats calculation and to blank the table, or re-enable the calculation."""
        self._stats_calculation_disabled = disable
        self._update_stats_disabled()
        if not disable:
            self._update_stats_task(0, True)  # populate the table again

    def _update_stats_disabled(self) -> None:
        """Updates the table visuals for stats disabled"""
        for row, name in enumerate(self._data_items.keys()):
            for col in self.STATS_COLS:
                item = not_none(self.item(row, self.COL_STAT + col))
                if self._stats_calculation_disabled:  # clear table on disable
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                    item.setText("")
                else:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled)

    def _on_stats_updated(
        self, input_arr: npt.NDArray[np.float64], input_region: Tuple[float, float], stats_dict: Dict[int, float]
    ) -> None:
        region = HasRegionSignalsTable._region_of_plot(self._plots)
        if input_region == self._FULL_RANGE:
            self._full_range_stats.set(input_arr, None, [], stats_dict)
        elif input_region == region:
            self._region_stats.set(input_arr, region, [], stats_dict)
        if input_region == region:  # update display as needed
            self._update_stats_display(False)

    def _update_stats_task(self, delay_ms: int, clear_table: bool) -> None:
        if self._stats_calculation_disabled:  # don't create a calculation task if disabled
            return

        region = HasRegionSignalsTable._region_of_plot(self._plots)
        data_items = [  # filter out enum types
            (name, (xs, ys)) for name, (xs, ys) in self._plots._data.items() if np.issubdtype(ys.dtype, np.number)
        ]
        if region == self._FULL_RANGE:  # for full range, deduplicate with cache
            needed_stats = [
                (weakref.ref(xs), weakref.ref(ys))
                for name, (xs, ys) in data_items
                if self._full_range_stats.get(ys, None, []) is None
            ]
        else:
            needed_stats = [(weakref.ref(xs), weakref.ref(ys)) for name, (xs, ys) in data_items]

        with QMutexLocker(self._request_mutex):
            self._request_data = needed_stats
            self._request_region = region
            if delay_ms > 0:
                self._debounce_target_ns = time.time_ns() + delay_ms * 1000000
        self._stats_threadpool.start(self.StatsCalculatorWorker(self))

        self._update_stats_display(clear_table)

    def _update_stats_display(self, clear_table: bool) -> None:
        if self._stats_calculation_disabled:  # don't update the display if disabled
            return

        for row, name in enumerate(self._data_items.keys()):
            xs, ys = self._plots._data.get(name, (None, None))
            if xs is None or ys is None:
                for col in self.STATS_COLS:
                    not_none(self.item(row, self.COL_STAT + col)).setText("")
                continue

            region = HasRegionSignalsTable._region_of_plot(self._plots)
            if region == self._FULL_RANGE:  # fetch from cache if available
                stats_dict: Dict[int, float] = self._full_range_stats.get(ys, None, [], {})
            else:  # slice
                stats_dict = self._region_stats.get(ys, region, [], {})

            for col_offset in self.STATS_COLS:
                item = not_none(self.item(row, self.COL_STAT + col_offset))
                if col_offset in stats_dict:
                    item.setText(self._plots.render_value(name, stats_dict[col_offset]))
                else:
                    if clear_table:
                        item.setText("")
