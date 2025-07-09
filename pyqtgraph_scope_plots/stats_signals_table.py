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
from functools import partial
from typing import Dict, Tuple, List, Any

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import Signal, QObject, QThread, QMutex, QMutexLocker
from PySide6.QtWidgets import QTableWidgetItem

from .signals_table import HasRegionSignalsTable
from .util import IdentityCacheDict, not_none


class StatsSignalsTable(HasRegionSignalsTable):
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

    _FULL_RANGE = (-float("inf"), float("inf"))

    class StatsCalculatorWorker(QObject):
        """Stats calculated in a separate thread to avoid blocking the main GUI thread when large regions
        are selected. The thread is persistent.
        This uses shared state variable to communicate the next computation task with a request signal to
        wake up the thread. Earlier, unserviced requests are clobbered."""

        request = Signal()
        update = Signal(object, object, object)  # input array, region, {stat (by offset col) -> value}

        def __init__(self):
            super().__init__()
            self._request_mutex = QMutex()
            self._request_data: List[
                Tuple[weakref.ref[npt.NDArray[np.float64]], weakref.ref[npt.NDArray[np.float64]]]
            ] = []
            self._last_data = self._request_data
            self._request_region: Tuple[float, float] = StatsSignalsTable._FULL_RANGE
            self._last_region = self._request_region
            self._debounce_target: int = 0  # earliest time to execute this task, for debouncing
            self.request.connect(self._process)

        def update_task(
            self,
            data: List[Tuple[weakref.ref[npt.NDArray[np.float64]], weakref.ref[npt.NDArray[np.float64]]]],
            region: Tuple[float, float],
            delay_ms: int,
        ) -> None:
            """Called from the main thread to update the task."""
            with QMutexLocker(self._request_mutex):
                self._request_data = data
                self._request_region = region
                if delay_ms > 0:
                    self._debounce_target = time.time_ns() + delay_ms * 1000000
            self.request.emit()

        # @Slot()
        def _process(self) -> None:
            """Runs an iteration of processing the request, if it is new."""
            with QMutexLocker(self._request_mutex):
                request_data = self._request_data
                request_region = self._request_region
                debounce_target = self._debounce_target
            if request_data == self._last_data and request_region == self._last_region:
                return
            delay_time = debounce_target - time.time_ns()
            if delay_time > 0:
                QThread.msleep(delay_time // 1000000)
                with QMutexLocker(self._request_mutex):
                    if request_data != self._request_data or request_region != self._request_region:
                        return  # data changed, run in next _process

            self._last_data = request_data
            self._last_region = request_region

            for xs_ys_ref in request_data:
                with QMutexLocker(self._request_mutex):
                    if self._debounce_target != debounce_target:
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
                self.update.emit(ys, request_region, stats_dict)
                QThread.yieldCurrentThread()  # yield the thread to ensure this is low priority

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
        super().__init__(*args, **kwargs)
        # since calculating stats across the full range is VERY EXPENSIVE, cache the results
        self._full_range_stats = IdentityCacheDict[npt.NDArray[np.float64], Dict[int, float]]()  # array -> stats dict
        self._region_stats = IdentityCacheDict[npt.NDArray[np.float64], Dict[int, float]]()  # array -> stats dict

        self._plots.sigDataUpdated.connect(lambda: self._update_stats_task(0))
        self._plots.sigCursorRangeChanged.connect(lambda: self._update_stats_task(100))

        stats_thread = QThread()  # not owned by this to allow this to be destroyed
        stats_thread.start(QThread.Priority.LowestPriority)
        self.destroyed.connect(partial(self._on_destroyed, stats_thread))

        self._stats_worker = self.StatsCalculatorWorker()
        self._stats_worker.moveToThread(stats_thread)
        self._stats_worker.update.connect(self._on_stats_updated)

    @staticmethod
    def _on_destroyed(thread_object: QThread):
        thread_object.quit()
        thread_object.wait()

    def _on_stats_updated(
        self, input_arr: npt.NDArray[np.float64], input_region: Tuple[float, float], stats_dict: Dict[int, float]
    ) -> None:
        region = HasRegionSignalsTable._region_of_plot(self._plots)
        if input_region == self._FULL_RANGE:
            self._full_range_stats.set(input_arr, None, [], stats_dict)
        elif input_region == region:
            self._region_stats.set(input_arr, region, [], stats_dict)
        if input_region == region:  # update display as needed
            self._update_stats_display()

    def _update_stats_task(self, delay_ms: int) -> None:
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

        self._stats_worker.update_task(needed_stats, region, delay_ms)
        self._update_stats_display()

    def _update_stats_display(self) -> None:
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
                if col_offset in stats_dict:
                    text_value = self._plots.render_value(name, stats_dict[col_offset])
                else:
                    text_value = ""
                not_none(self.item(row, self.COL_STAT + col_offset)).setText(text_value)
