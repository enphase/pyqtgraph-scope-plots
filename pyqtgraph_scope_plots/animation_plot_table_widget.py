from PySide6.QtWidgets import QInputDialog, QFileDialog

from .plots_table_widget import PlotsTableWidget


class AnimationPlotsTableWidget(PlotsTableWidget):
    """A PlotTableWidget that provides a function for generating an animation from the plot windows.
    This function handles the UI flow for generating an animation, but does not provide the controls
    to initiate this flow (which is left up to the subclass to implement)"""

    FRAMES_PER_SEGMENT = 8  # TODO these should be user-configurable
    MS_PER_FRAME = 100

    def _start_animation_ui_flow(self) -> None:
        region_percentage, ok = QInputDialog().getDouble(
            self, "Animation", "Region percentage per frame", 10, minValue=0, maxValue=100
        )
        if not ok:
            return
        filename, filter = QFileDialog.getSaveFileName(self, f"Animation", "", "Animated GIF (*.gif)")
        if not filename:
            return

        if isinstance(self._plots._last_region, tuple):
            full_region = self._plots._last_region
            restore_full_region = True
        else:
            all_xs = [data[0] for data in self._transformed_data.values()]
            min_xs = [min(data) for data in all_xs if len(data)]
            max_xs = [max(data) for data in all_xs if len(data)]
            assert min_xs or max_xs, "no data to determine full region"
            full_region = (min(min_xs), max(max_xs))
            restore_full_region = False
        assert full_region[1] > full_region[0], "empty region"

        frames_count = self.FRAMES_PER_SEGMENT * (100 / region_percentage)

        with open(filename, "w", newline="") as f:
            pass

        if restore_full_region:
            self._plots._on_region_change(full_region, None)
        else:
            self._plots._on_region_change(None, None)
