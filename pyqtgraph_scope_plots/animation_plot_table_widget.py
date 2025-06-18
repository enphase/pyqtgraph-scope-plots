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

from typing import List

from PySide6 import QtGui
from PySide6.QtWidgets import QInputDialog, QFileDialog, QWidget
from PIL import Image

from .multi_plot_widget import LinkedMultiPlotWidget
from .xy_plot_table import XyTable
from .plots_table_widget import PlotsTableWidget


class AnimationPlotsTableWidget(PlotsTableWidget):
    """A PlotTableWidget that provides a function for generating an animation from the plot windows.
    This function handles the UI flow for generating an animation, but does not provide the controls
    to initiate this flow (which is left up to the subclass to implement).

    Plots must be LinkedMultiPlotWidget"""

    FRAMES_PER_SEGMENT = 8  # TODO these should be user-configurable
    MS_PER_FRAME = 50

    def _start_animation_ui_flow(self, default_filename: str = "") -> None:
        assert isinstance(self._plots, LinkedMultiPlotWidget)

        region_percentage, ok = QInputDialog().getDouble(
            self, "Animation", "Region percentage per frame", 10, minValue=0, maxValue=100
        )
        if not ok:
            return

        if isinstance(self._plots._last_region, tuple):
            full_region = self._plots._last_region
            restore_full_region = True
        else:
            all_xs = [data[0] for data in self._plots._data.values()]
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

        capture_windows: List[QWidget] = [self._plots]
        if isinstance(self._table, XyTable):
            for widget in self._table._xy_plots:
                capture_windows.append(widget.get_plot_widget())

        images = []
        for i in range(frames_count):
            frame_center = full_region[0] + (frame_size / 2) + (i / (frames_count - 1) * sliding_region_size)
            self._plots._on_region_change(None, (frame_center - frame_size / 2, frame_center + frame_size / 2))
            QtGui.QGuiApplication.processEvents()

            window_images = []
            for window in capture_windows:
                window_images.append(Image.fromqpixmap(window.grab()))

            combined_width = sum(image.width for image in window_images)
            combined_height = max(image.height for image in window_images)
            combined_image = Image.new("RGB", (combined_width, combined_height))
            x_offset = 0
            for image in window_images:
                combined_image.paste(image, (x_offset, 0))
                x_offset += image.width
            images.append(combined_image)

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
