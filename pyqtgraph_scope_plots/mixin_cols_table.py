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

import bisect
from typing import Dict, Tuple, List, Any, Optional

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import QMimeData, QPoint, Signal
from PySide6.QtGui import QColor, Qt, QAction, QDrag, QPixmap, QMouseEvent
from PySide6.QtWidgets import QTableWidgetItem, QTableWidget, QHeaderView, QMenu, QLabel

from .multi_plot_widget import MultiPlotWidget, LinkedMultiPlotWidget
from .util import not_none


class MixinColsTable(QTableWidget):
    """A base class that provides infrastructure for mixins to contribute columns into a QTableWidget"""
    COL_COUNT: int = 0

