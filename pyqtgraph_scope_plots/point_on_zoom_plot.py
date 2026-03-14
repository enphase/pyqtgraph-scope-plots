# Copyright 2026 Enphase Energy, Inc.
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

"""
Mixin for PlotItem that draws points at each data point when zoomed in enough.
"""

import bisect
from abc import abstractmethod
from typing import Dict, List, Optional, Any, Tuple, Mapping

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QTimer
from PySide6.QtGui import QColor
from numpy import typing as npt

from .enum_waveform_plotitem import EnumWaveformPlot
from .interactivity_mixins import DataPlotCurveItem, DataPlotItem


class BasePointOnZoomPlot(DataPlotItem):
    """Base mixin that provides some infrastructure for point-on-zoom functionality.

    Points are shown when the minimum spacing between data points on the X axis
    exceeds MIN_POINT_SPACING_PX pixels. This is dynamic and responds to zoom changes
    and data updates."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # range update may be called before mapFromView produces updated results, so defer the update
        self._pending_range_update = False
        self._range_update_timer = QTimer(self)
        self._range_update_timer.setSingleShot(True)
        self._range_update_timer.timeout.connect(self._do_range_update)
        self.getViewBox().sigRangeChanged.connect(self._on_range_changed)

    @abstractmethod
    def _update_points(self, name: str, xs: npt.NDArray[np.float64], ys: npt.NDArray) -> None:
        """Update point visibility and data for a specific data item based on current zoom.
        This may be called in response to new data or changed zoom."""
        raise NotImplementedError

    def _update_plot_data(self, name: str, xs: npt.NDArray[np.float64], ys: npt.NDArray) -> None:
        super()._update_plot_data(name, xs, ys)
        self._update_points(name, xs, ys)

    def _on_range_changed(self) -> None:
        if self._pending_range_update:
            return
        self._pending_range_update = True

        self._range_update_timer.start(0)

    def _do_range_update(self) -> None:
        self._pending_range_update = False
        for name, (xs, ys) in self._data.items():
            scatter = self._point_scatters.get(name)
            if scatter is None:
                continue
            self._update_points(name, xs, ys)

    def _calculate_visible_indices(self, xs: npt.NDArray[np.float64]) -> Optional[Tuple[int, int]]:
        """Calculate start and end indices of points to show, if zoomed in enough"""
        viewbox = self.getViewBox()
        view_x_range = viewbox.viewRange()[0]
        start_idx = bisect.bisect_left(xs, view_x_range[0])
        end_idx = bisect.bisect_right(xs, view_x_range[1])

        if start_idx >= end_idx:
            return None

        visible_count = end_idx - start_idx
        if visible_count <= 1:
            return (start_idx, end_idx)

        # Fast first-pass: check average spacing to do a quick reject
        widget_width = viewbox.width()
        if widget_width <= 0:
            return None
        average_spacing = widget_width / (visible_count - 1)
        if average_spacing < self.MIN_POINT_SPACING_PX:
            return None

        # Check minimum-spacing between points using current view transform
        pixel_x_coords = [self.mapFromView(QPointF(x, 0)).x() for x in xs[start_idx:end_idx]]
        spacings = [abs(pixel_x_coords[i + 1] - pixel_x_coords[i]) for i in range(len(pixel_x_coords) - 1)]
        if not spacings:
            return (start_idx, end_idx)
        min_spacing = min(spacings)
        if min_spacing >= self.MIN_POINT_SPACING_PX:
            return (start_idx, end_idx)
        else:
            return None


class PointOnZoomPlot(DataPlotCurveItem, BasePointOnZoomPlot):
    """Mixin for PlotItem that draws points at each data point when zoomed in enough."""

    # Configurable constant: minimum pixel spacing between points to show them
    MIN_POINT_SPACING_PX: float = 8.0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._point_scatters: Dict[str, pg.ScatterPlotItem] = {}

    def _generate_plot_items(self, data_items: Mapping[str, QColor]) -> Dict[str, List[pg.GraphicsObject]]:
        parent_graphics = super()._generate_plot_items(data_items)

        self._point_scatters.clear()
        for name, color in data_items.items():
            scatter = pg.ScatterPlotItem(
                x=[],
                y=[],
                pen=color,
                brush=color,
                size=4,
            )
            scatter.hide()  # Initially hidden
            parent_graphics[name].append(scatter)
            self._point_scatters[name] = scatter

        return parent_graphics

    def _update_points(self, name: str, xs: npt.NDArray[np.float64], ys: npt.NDArray) -> None:
        points_to_show = self._calculate_visible_indices(xs)
        scatter = self._point_scatters[name]
        if points_to_show is None:
            scatter.hide()
        else:
            start_idx, end_idx = points_to_show
            visible_xs = xs[start_idx:end_idx]
            visible_ys = ys[start_idx:end_idx]
            scatter.setData(x=visible_xs, y=visible_ys)
            scatter.show()


class EnumPointOnZoomPlot(EnumWaveformPlot, BasePointOnZoomPlot):
    """Mixin for PlotItem that draws points at each data point when zoomed in enough."""

    # Configurable constant: minimum pixel spacing between points to show them
    MIN_POINT_SPACING_PX: float = 8.0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._point_scatters: Dict[str, pg.ScatterPlotItem] = {}

    def _generate_plot_items(self, data_items: Mapping[str, QColor]) -> Dict[str, List[pg.GraphicsObject]]:
        parent_graphics = super()._generate_plot_items(data_items)

        self._point_scatters.clear()
        for name, color in data_items.items():
            scatter = pg.ScatterPlotItem(
                x=[],
                y=[],
                pen=color,
                brush=color,
                size=4,
            )
            scatter.hide()  # Initially hidden
            parent_graphics[name].append(scatter)
            self._point_scatters[name] = scatter

        return parent_graphics

    def _update_points(self, name: str, xs: npt.NDArray[np.float64], ys: npt.NDArray) -> None:
        points_to_show = self._calculate_visible_indices(xs)
        scatter = self._point_scatters[name]
        if points_to_show is None:
            scatter.hide()
        else:
            start_idx, end_idx = points_to_show
            visible_xs = xs[start_idx:end_idx]
            ys_true = np.ones(end_idx - start_idx)
            ys_comp = -np.ones(end_idx - start_idx)
            scatter.setData(x=np.concatenate([visible_xs, visible_xs]), y=np.concatenate([ys_true, ys_comp]))
            scatter.show()
