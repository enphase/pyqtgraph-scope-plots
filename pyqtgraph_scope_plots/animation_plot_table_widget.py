from PySide6.QtWidgets import QInputDialog, QFileDialog

from .plots_table_widget import PlotsTableWidget


class AnimationPlotsTableWidget(PlotsTableWidget):
    """A PlotTableWidget that provides a function for generating an animation from the plot windows.
    This function handles the UI flow for generating an animation, but does not provide the controls
    to initiate this flow (which is left up to the subclass to implement)"""

    FRAMES_PER_SEGMENT = 8  # TODO these should be user-configurable
    MS_PER_FRAME = 100

    def _start_animation_ui_flow(self):
        value, ok = QInputDialog().getDouble(
            self, "Animation", "Region percentage per frame", 10, minValue=0, maxValue=100
        )
        if not ok:
            return
        filename, filter = QFileDialog.getSaveFileName(self, f"Animation", "", "Animated GIF (*.gif)")
        if not filename:
            return

        with open(filename, "w", newline="") as f:
            pass
