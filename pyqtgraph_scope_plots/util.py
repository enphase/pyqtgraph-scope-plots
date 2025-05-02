from typing import Any, TypeVar, Optional, overload, cast

import pyqtgraph as pg
from PySide6.QtGui import QColor


NotNoneType = TypeVar("NotNoneType")


@overload
def not_none(x: Optional[Any]) -> Any: ...
@overload
def not_none(x: Optional[NotNoneType]) -> NotNoneType: ...
def not_none(x: Optional[NotNoneType]) -> NotNoneType:
    assert x is not None
    return x


def int_color(index: int) -> QColor:
    """Custom intColor that drops blue (every 7 out of 9 indices) since it's not legible at all"""
    return cast(QColor, pg.intColor(index + (index - 6 + 8) // 8))
