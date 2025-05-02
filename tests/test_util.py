from typing import TypeVar, Type, Any, cast

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QAction
from PySide6.QtWidgets import *
from pytestqt.qtbot import QtBot

CastTarget = TypeVar('CastTarget')
def assert_cast(tpe: Type[CastTarget], obj: Any) -> CastTarget:
    """A static cast that also does a runtime type check"""
    assert isinstance(obj, tpe), f"{obj} not of type {tpe}"
    return obj  # type: ignore


def context_menu(qtbot: QtBot, container: QWidget, target: QPoint = QPoint(0, 0)) -> QMenu:
    """Opens up a context menu at the container and optional point, assert it opened, and returns the menu.
    """
    if hasattr(container, 'viewport'):  # some widgets don't support viewport and don't seen to need this
        qtbot.mouseClick(container.viewport(), Qt.MouseButton.RightButton, pos=target)  # set cursor target
    prev_menu = container.findChild(QMenu)
    if prev_menu is not None:
        cast(QMenu, prev_menu).deleteLater()  # clear out the prior menu so the new one can be found
        qtbot.waitUntil(lambda: container.findChild(QMenu) is None)
    container.customContextMenuRequested.emit(target)
    qtbot.waitUntil(lambda: container.findChild(QMenu) is not None)
    return assert_cast(QMenu, container.findChild(QMenu))


def menu_action_by_name(menu: QMenu, *text: str) -> QAction:
    """Given a menu, returns the first action that contains the specified text, case-insensitive"""
    for i, current_text in enumerate(text):
        item_found = False
        for action in menu.actions():
            if current_text.lower() in action.text().lower():
                item_found = True
                if i < len(text) - 1:  # iterate through submenu
                    menu = menu.menuInAction(action)
                else:  # final step, return the action
                    return action
        if not item_found:
            raise ValueError(f"No menu item with {current_text} in {[action.text() for action in menu.actions()]}")
    raise ValueError()  # shouldn't happen, here to satisfy the type checker
