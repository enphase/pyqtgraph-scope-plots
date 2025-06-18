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

from typing import Any, TypeVar, Optional, overload, cast

import pyqtgraph as pg
from PySide6.QtGui import QColor


NotNoneType = TypeVar("NotNoneType")


@overload
def not_none(x: Optional[Any]) -> Any:
    ...


@overload
def not_none(x: Optional[NotNoneType]) -> NotNoneType:
    ...


def not_none(x: Optional[NotNoneType]) -> NotNoneType:
    assert x is not None
    return x


def int_color(index: int) -> QColor:
    """Custom intColor that drops blue (every 7 out of 9 indices) since it's not legible at all"""
    return cast(QColor, pg.intColor(index + (index - 6 + 8) // 8))
