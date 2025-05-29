from typing import List

from PySide6 import QtGui
from PySide6.QtWidgets import QInputDialog, QFileDialog, QWidget
from PIL import Image

from .plots_table_widget import PlotsTableWidget


class AnimationPlotsTableWidget(PlotsTableWidget):
    """A PlotTableWidget that provides a function for generating an animation from the plot windows.
    This function handles the UI flow for generating an animation, but does not provide the controls
    to initiate this flow (which is left up to the subclass to implement)"""

    FRAMES_PER_SEGMENT = 4  # TODO these should be user-configurable
    MS_PER_FRAME = 50

    def _start_animation_ui_flow(self, default_filename: str = "") -> None:
        region_percentage, ok = QInputDialog().getDouble(
            self, "Animation", "Region percentage per frame", 10, minValue=0, maxValue=100
        )
        if not ok:
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

        region_size = full_region[1] - full_region[0]
        frame_size = region_size * (region_percentage / 100)
        sliding_region_size = region_size - frame_size
        frames_count = int(self.FRAMES_PER_SEGMENT * (100 / region_percentage))

        capture_windows: List[QWidget] = [self]
        print(self.size())
        images = []
        for i in range(frames_count):
            frame_center = full_region[0] + (frame_size / 2) + (i / (frames_count - 1) * sliding_region_size)
            print(i, frame_center, (frame_center - frame_size / 2, frame_center + frame_size / 2))
            self._plots._on_region_change(None, (frame_center - frame_size / 2, frame_center + frame_size / 2))
            QtGui.QGuiApplication.processEvents()
            image = Image.fromqpixmap(self.grab())
            images.append(image)

        if restore_full_region:
            self._plots._on_region_change(None, full_region)
        else:
            self._plots._on_region_change(None, None)

        filename, filter = QFileDialog.getSaveFileName(
            self, f"Save Animation", default_filename, "Animated GIF (*.gif)"
        )
        if not filename:
            return
        images[0].save(filename, save_all=True, append_images=images[1:], duration=self.MS_PER_FRAME, loop=0)
