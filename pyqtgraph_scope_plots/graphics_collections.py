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
"""Wrapper classes for collections of graphical objects."""
from typing import List, Tuple, Optional

import pyqtgraph as pg
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor


class TextItemCollection:
    """Maintains a pool of TextItems that persist across refreshes (for efficiency)"""

    def __init__(
        self, parent: pg.PlotItem, *, anchor: Optional[Tuple[float, float]] = None, z_value: Optional[float] = None
    ) -> None:
        self._parent = parent
        self._anchor = anchor
        self._z_value = z_value

        self._labels: List[pg.TextItem] = []

    def update(self, pts: List[Tuple[float, float, str, QColor]]) -> None:
        while len(self._labels) != len(pts):  # create or delete as needed
            if len(self._labels) < len(pts):
                label = pg.TextItem()
                if self._anchor is not None:
                    label.setAnchor(self._anchor)
                if self._z_value is not None:
                    label.setZValue(self._z_value)
                self._parent.addItem(label, ignoreBounds=True)
                self._labels.append(label)
            else:
                self._parent.removeItem(self._labels.pop())

        for text_item, (x_pos, y_pos, text, color) in zip(self._labels, pts):
            text_item.setPos(QPointF(x_pos, y_pos))
            text_item.setText(text)
            text_item.setColor(color)

    def remove(self) -> None:
        """Removes all labels from the container. Call before this item is deleted."""
        while len(self._labels):
            self._parent.removeItem(self._labels.pop())


class ScatterItemCollection:
    """Presents a unified API drawing multiple points into a single scatterplot (for efficiency)"""

    def __init__(self, parent: pg.PlotItem, *, z_value: Optional[float] = None) -> None:
        self._parent = parent
        self._scatter = pg.ScatterPlotItem(x=[], y=[], symbol="o")
        if z_value is not None:
            self._scatter.setZValue(z_value)
        self._parent.addItem(self._scatter, ignoreBounds=True)

    def update(self, pts: List[Tuple[float, float, QColor]]) -> None:
        if len(pts) > 0:  # convert the list-of-tuples into a lists of point values for scatterplot format
            x_poss, y_poss, colors = tuple(map(list, zip(*pts)))
        else:  # zip returns empty for empty inputs
            x_poss, y_poss, colors = [], [], []
        self._scatter.setData(x=x_poss, y=y_poss, brush=colors)

    def remove(self) -> None:
        """Removes the scatter points from the container. Call before this item is deleted."""
        self._parent.removeItem(self._scatter)
