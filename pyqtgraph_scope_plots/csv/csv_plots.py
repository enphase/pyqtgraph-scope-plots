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

import itertools
import os.path
import time
from functools import partial
from typing import Dict, Tuple, Any, List, Optional, Callable, Sequence, cast, Set, Iterable, Type, Union, TextIO

import numpy as np
import numpy.typing as npt
import pandas as pd
import pyqtgraph as pg
import yaml
from PySide6 import QtWidgets
from PySide6.QtCore import QKeyCombination, QTimer, QSettings
from PySide6.QtGui import QAction, Qt
from PySide6.QtWidgets import (
    QWidget,
    QPushButton,
    QFileDialog,
    QMenu,
    QVBoxLayout,
    QInputDialog,
    QToolButton,
    QMessageBox,
)
from pydantic import BaseModel, ValidationError

from ..legend_plot_widget import LegendPlotWidget
from ..xy_plot_legends import XyTableLegends
from ..xy_plot_visibility import VisibilityXyPlotWidget, VisibilityXyPlotTable
from ..visibility_toggle_table import VisibilityToggleSignalsTable, VisibilityPlotWidget
from ..animation_plot_table_widget import AnimationPlotsTableWidget
from ..color_signals_table import ColorPickerSignalsTable, ColorPickerPlotWidget
from ..multi_plot_widget import MultiPlotWidget
from ..plots_table_widget import PlotsTableWidget
from ..util import int_color, BaseTopModel, HasSaveLoadDataConfig
from ..filter_signals_table import FilterSignalsTable
from ..stats_signals_table import StatsSignalsTable
from ..time_axis import TimeAxisItem
from ..timeshift_signals_table import TimeshiftSignalsTable, TimeshiftPlotWidget
from ..transforms_signal_table import TransformsSignalsTable, TransformsPlotWidget
from ..xy_plot import (
    XyPlotWidget,
    XyDragDroppable,
    DeleteableXyPlotTable,
    SignalRemovalXyPlotTable,
    XyPlotTable,
    XyPlotLinkedCursorWidget,
    XyPlotLinkedPoiWidget,
)
from ..xy_plot_table import XyTable
from ..xy_plot_splitter import XyPlotSplitter
from ..xy_plot_refgeo import RefGeoXyPlotWidget, RefGeoXyPlotTable


class TupleSafeLoader(yaml.SafeLoader):
    pass


def construct_python_tuple(loader: TupleSafeLoader, node: Any) -> Tuple[Any, ...]:
    return tuple(loader.construct_sequence(node))


TupleSafeLoader.add_constructor("tag:yaml.org,2002:python/tuple", construct_python_tuple)


class CsvLoaderStateModel(BaseTopModel):
    csv_files: Optional[List[str]] = None  # all loaded CSV files, as relpath or abspath


class FullXySplitter(XyPlotSplitter):
    class FullXyPlot(
        VisibilityXyPlotWidget,
        RefGeoXyPlotWidget,
        XyDragDroppable,
        XyPlotLinkedCursorWidget,
        XyPlotLinkedPoiWidget,
        XyPlotWidget,
    ):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._thickness: float = 1
            super().__init__(*args, **kwargs)

        def _update(self) -> None:
            super()._update()
            for item in self.items():
                if isinstance(item, pg.PlotCurveItem):
                    item.setPen(color=item.opts["pen"].color(), width=self._thickness)

        def set_thickness(self, thickness: float) -> None:
            self._thickness = thickness
            self._update()

    class FullXyPlotTable(
        VisibilityXyPlotTable, RefGeoXyPlotTable, SignalRemovalXyPlotTable, DeleteableXyPlotTable, XyPlotTable
    ):
        pass

    _XY_PLOT_TYPE = FullXyPlot
    _XY_PLOT_TABLE_TYPE = FullXyPlotTable

    def set_thickness(self, thickness: float) -> None:
        assert isinstance(self._xy_plots, self.FullXyPlot)
        self._xy_plots.set_thickness(thickness)


class FullPlots(
    LegendPlotWidget,
    VisibilityPlotWidget,
    ColorPickerPlotWidget,
    TimeshiftPlotWidget,
    TransformsPlotWidget,
    PlotsTableWidget.Plots,
):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._thickness: float = 1
        super().__init__(*args, **kwargs)

    def _update_plots(self) -> None:
        super()._update_plots()
        for plot_item, _ in self._plot_item_data.items():
            for item in plot_item.items:
                if isinstance(item, pg.PlotCurveItem):
                    item.setPen(color=item.opts["pen"].color(), width=self._thickness)

    def set_thickness(self, thickness: float) -> None:
        self._thickness = thickness
        self._update_plots()


class FullSignalsTable(
    VisibilityToggleSignalsTable,
    XyTableLegends,
    XyTable,
    ColorPickerSignalsTable,
    TimeshiftSignalsTable,
    TransformsSignalsTable,
    FilterSignalsTable,
    StatsSignalsTable,
    PlotsTableWidget.SignalsTable,
):
    """Adds a hook for item hide"""

    _XY_PLOT_TYPE = FullXySplitter

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._remove_row_action = QAction("Remove from Plot", self)
        self._remove_row_action.triggered.connect(self._on_rows_remove)

    def _on_rows_remove(self) -> None:
        rows = list(set([item.row() for item in self.selectedItems()]))
        ordered_names = list(self._data_items.keys())
        data_names = [ordered_names[row] for row in rows]
        self._plots.remove_plot_items(data_names)

    def _populate_context_menu(self, menu: QMenu) -> None:
        super()._populate_context_menu(menu)
        menu.addAction(self._remove_row_action)

    def set_thickness(self, thickness: float) -> None:
        for xy_plot in self._xy_plots:
            assert isinstance(xy_plot, FullXySplitter)
            xy_plot.set_thickness(thickness)


class CsvLoaderRecents(BaseModel):
    hotkeys: Dict[int, str] = {}  # hotkey number -> file
    recents: List[str] = []  # most recent first


class CsvLoaderPlotsTableWidget(AnimationPlotsTableWidget, PlotsTableWidget, HasSaveLoadDataConfig):
    """Example app-level widget that loads CSV files into the plotter"""

    _MODEL_BASES = [CsvLoaderStateModel]

    WATCH_INTERVAL_MS = 333  # polls the filesystem metadata for changes this frequently
    _RECENTS_MAX = 9  # hotkeys + recents is pruned to this count
    _RECENTS_CONFIG_KEY = "recents"  # for QSettings

    _PLOT_TYPE = FullPlots
    _TABLE_TYPE = FullSignalsTable

    @classmethod
    def _config(cls) -> QSettings:  # for unit testability
        return QSettings("scope-plots", "csv")

    def __init__(self, x_axis: Optional[Callable[[], pg.AxisItem]] = None) -> None:
        self._x_axis = x_axis
        self._loaded_config_abspath = ""  # of last loaded config file, even if it has changed

        super().__init__()

        self._table: CsvLoaderPlotsTableWidget.SignalsTable

        # since this can load multiple CSVs simultaneously, store the data here
        self._data_items: Dict[str, MultiPlotWidget.PlotType] = {}  # col header -> plot type IF NOT Default
        self._data: Dict[str, Tuple[np.typing.ArrayLike, np.typing.ArrayLike]] = {}  # col header -> xs, ys
        self._csv_data_items: Dict[str, Set[str]] = {}  # csv path -> data name
        self._csv_time: Dict[str, float] = {}  # csv path -> load time
        self._watch_timer = QTimer()
        self._watch_timer.setInterval(self.WATCH_INTERVAL_MS)
        self._watch_timer.timeout.connect(self._check_watch)

    @classmethod
    def _get_all_model_bases(cls) -> List[Type[BaseModel]]:
        bases = super()._get_all_model_bases()
        plot_bases = cls._PLOT_TYPE._get_all_model_bases()
        table_bases = cls._TABLE_TYPE._get_all_model_bases()
        return bases + plot_bases + table_bases

    @classmethod
    def _get_data_model_bases(cls) -> List[Type[BaseModel]]:
        bases = super()._get_data_model_bases()
        plot_bases = cls._PLOT_TYPE._get_data_model_bases()
        table_bases = cls._TABLE_TYPE._get_data_model_bases()
        return bases + plot_bases + table_bases

    def _write_model(self, model: BaseModel) -> None:
        super()._write_model(model)
        assert isinstance(self._table, HasSaveLoadDataConfig)
        self._table._write_model(model)
        self._plots._write_model(model)

    def _load_model(self, model: BaseModel) -> None:
        super()._load_model(model)
        assert isinstance(self._table, HasSaveLoadDataConfig)
        self._table._load_model(model)
        self._plots._load_model(model)

    def _on_legend_checked(self) -> None:
        assert isinstance(self._plots, FullPlots)
        assert isinstance(self._table, FullSignalsTable)
        self._legend_action.setDisabled(True)  # pyqtgraph doesn't support deleting legends
        self._plots.show_legends()
        self._table.show_legends()

    def _on_line_width_action(self) -> None:
        assert isinstance(self._plots, FullPlots)
        assert isinstance(self._table, FullSignalsTable)
        value, ok = QInputDialog().getDouble(
            self, "Set thickness", "Line thickness", self._plots._thickness, minValue=0
        )
        if not ok:
            return
        self._plots.set_thickness(value)
        self._table.set_thickness(value)

    def _on_disable_stats(self, checked: bool) -> None:
        assert isinstance(self._table, StatsSignalsTable)
        self._table.disable_stats(checked)

    def _make_controls(self) -> QWidget:
        button_load = QToolButton()
        button_load.setText("Load CSV")
        button_load.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button_load.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        button_load.clicked.connect(self._on_load_csv)

        menu_load = QMenu(self)
        action_append = QAction(menu_load)
        action_append.setText("Append CSV")
        action_append.triggered.connect(self._on_append_csv)
        menu_load.addAction(action_append)
        button_load.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        button_load.setArrowType(Qt.ArrowType.DownArrow)
        button_load.setMenu(menu_load)

        button_load_config = QToolButton()
        button_load_config.setText("Load Config")
        button_load_config.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button_load_config.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        button_load_config.clicked.connect(self._on_load_config)

        self._menu_config = QMenu(self)
        button_load_config.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        button_load_config.setArrowType(Qt.ArrowType.DownArrow)
        button_load_config.setMenu(self._menu_config)
        self._menu_config.aboutToShow.connect(self._populate_config_menu)

        self._load_hotkey_actions = []
        for i in range(10):
            load_hotkey_action = QAction(f"", self)
            load_hotkey_action.setShortcut(
                QKeyCombination(Qt.KeyboardModifier.ControlModifier, Qt.Key(Qt.Key.Key_0 + i))
            )
            load_hotkey_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            load_hotkey_action.triggered.connect(partial(self._load_hotkey_slot, i))
            self.addAction(load_hotkey_action)
            self._load_hotkey_actions.append(load_hotkey_action)

        button_refresh = QToolButton()
        button_refresh.setText("Refresh CSV")
        button_refresh.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button_refresh.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        button_refresh.clicked.connect(self._on_refresh_csv)

        menu_refresh = QMenu(self)
        self._action_watch = QAction(menu_refresh)
        self._action_watch.setText("Set Watch")
        self._action_watch.setCheckable(True)
        self._action_watch.toggled.connect(self._on_toggle_watch)
        menu_refresh.addAction(self._action_watch)
        button_refresh.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        button_refresh.setArrowType(Qt.ArrowType.DownArrow)
        button_refresh.setMenu(menu_refresh)

        # hotkey shortcut for refresh
        action_refresh = QAction(self)
        action_refresh.setShortcut(QKeyCombination(Qt.KeyboardModifier.ShiftModifier, Qt.Key.Key_F5))
        action_refresh.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        action_refresh.triggered.connect(self._on_refresh_csv)
        self.addAction(action_refresh)

        button_visuals = QPushButton("Visual Settings")
        button_menu = QMenu(self)
        self._legend_action = QAction("Show Legend", button_menu)
        self._legend_action.setCheckable(True)
        self._legend_action.toggled.connect(self._on_legend_checked)
        button_menu.addAction(self._legend_action)
        line_width_action = QAction("Set Line Width", button_menu)
        line_width_action.triggered.connect(self._on_line_width_action)
        button_menu.addAction(line_width_action)
        self._disable_stats_action = QAction("Disable Stats", button_menu)
        self._disable_stats_action.setCheckable(True)
        self._disable_stats_action.toggled.connect(self._on_disable_stats)
        button_menu.addAction(self._disable_stats_action)
        animation_action = QAction("Create Animation", button_menu)
        animation_action.triggered.connect(partial(self._start_animation_ui_flow, ""))
        button_menu.addAction(animation_action)
        button_visuals.setMenu(button_menu)

        layout = QVBoxLayout()
        layout.addWidget(button_load)
        layout.addWidget(button_load_config)
        layout.addWidget(button_refresh)
        layout.addWidget(button_visuals)
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def _get_recents(self) -> CsvLoaderRecents:
        recents_val = cast(str, self._config().value(self._RECENTS_CONFIG_KEY, ""))
        try:
            return CsvLoaderRecents.model_validate(CsvLoaderRecents(**yaml.load(recents_val, Loader=TupleSafeLoader)))
        except (yaml.YAMLError, TypeError, ValidationError):
            return CsvLoaderRecents()

    def _populate_config_menu(self) -> None:
        self._menu_config.clear()
        save_config_action = QAction("Save Config", self._menu_config)
        save_config_action.triggered.connect(self._on_save_config)
        self._menu_config.addAction(save_config_action)

        self._menu_config.addSeparator()
        recents = self._get_recents()
        for hotkey, recent in sorted(recents.hotkeys.items(), key=lambda x: x[0]):
            load_hotkey_action = self._load_hotkey_actions[hotkey]  # crash on invalid index
            load_hotkey_action.setText(f"{os.path.split(recent)[1]}")
            self._menu_config.addAction(load_hotkey_action)

        for recent in recents.recents:
            load_action = QAction(f"{os.path.split(recent)[1]}", self._menu_config)
            load_action.triggered.connect(partial(self.load_config_file, recent))
            self._menu_config.addAction(load_action)

        self._menu_config.addSeparator()
        set_hotkey_action = QAction("Set Hotkey", self._menu_config)
        set_hotkey_action.triggered.connect(self._on_set_hotkey)
        if self._loaded_config_abspath:
            set_hotkey_action.setText(f"Set Hotkey for {os.path.split(self._loaded_config_abspath)[1]}")
        else:
            set_hotkey_action.setDisabled(True)
        self._menu_config.addAction(set_hotkey_action)

    def _on_set_hotkey(self) -> None:
        assert self._loaded_config_abspath  # shouldn't be triggerable unless something loaded
        recents = self._get_recents()

        hotkey, ok = QInputDialog.getInt(self, "Set Hotkey Slot", "", value=0, minValue=0, maxValue=9)
        if not ok:
            return

        if self._loaded_config_abspath in recents.recents:
            recents.recents.remove(self._loaded_config_abspath)
        recents.hotkeys[hotkey] = self._loaded_config_abspath
        self._config().setValue(self._RECENTS_CONFIG_KEY, yaml.dump(recents.model_dump(), sort_keys=False))

    def _load_hotkey_slot(self, slot: int) -> None:
        recents = self._get_recents()
        target = recents.hotkeys.get(slot, None)
        if target is not None:
            self.load_config_file(target)

    def _append_recent(self) -> None:
        recents = self._get_recents()
        if self._loaded_config_abspath in recents.hotkeys.values():
            return  # don't overwrite hotkeys
        if self._loaded_config_abspath in recents.recents:
            recents.recents.remove(self._loaded_config_abspath)
        recents.recents.insert(0, self._loaded_config_abspath)
        excess_recents = len(recents.recents) + len(recents.hotkeys) - self._RECENTS_MAX
        if excess_recents > 0:
            recents.recents = recents.recents[:-excess_recents]

        self._config().setValue(self._RECENTS_CONFIG_KEY, yaml.dump(recents.model_dump(), sort_keys=False))

    def _on_load_csv(self) -> None:
        csv_filenames, _ = QFileDialog.getOpenFileNames(None, "Select CSV Files", filter="CSV files (*.csv)")
        if not csv_filenames:  # nothing selected, user canceled
            return
        self._load_csvs(csv_filenames)

    def _on_append_csv(self) -> None:
        csv_filenames, _ = QFileDialog.getOpenFileNames(None, "Select CSV Files", filter="CSV files (*.csv)")
        if not csv_filenames:  # nothing selected, user canceled
            return
        self._load_csvs(csv_filenames, append=True)

    def _on_refresh_csv(self) -> None:
        """Reloads all CSVs. Discards data (but not data items) that are no longer present in the reloaded CSVs.
        Does not modify data items (new data items are discarded)."""
        self._load_csvs(
            list(self._csv_data_items.keys()),
            colnames=itertools.chain(*self._csv_data_items.values()),
            append=True,
        )

    def _on_toggle_watch(self) -> None:
        if self._action_watch.isChecked():
            self._watch_timer.start()
        else:
            self._watch_timer.stop()

    def _check_watch(self) -> None:
        files_to_load: List[str] = []  # aggregate items to load for batch loading
        data_items_to_load: List[str] = []
        for csv_filepath, curr_data_items in self._csv_data_items.items():
            if csv_filepath not in self._csv_time:  # skip files where the load time is unknown
                continue
            if not os.path.exists(csv_filepath):  # ignore transiently missing files
                continue
            if os.path.getmtime(csv_filepath) <= self._csv_time[csv_filepath]:
                continue

            files_to_load.append(csv_filepath)
            data_items_to_load.extend(curr_data_items)

        if files_to_load:
            self._load_csvs(files_to_load, colnames=data_items_to_load, append=True)

    def load_csvs(self, csv_filepaths: List[str], *, append: bool = False) -> None:
        """Public API for loading CSV files"""
        self._load_csvs(csv_filepaths, append=append)

    def _load_csvs(
        self,
        csv_filepaths: List[str],
        append: bool = False,
        colnames: Optional[Iterable[str]] = None,
        update: bool = True,
    ) -> "CsvLoaderPlotsTableWidget":
        """Loads CSV files into the current window.
        If append is true, preserves the existing data / metadata.
        If colnames is not None, reads the specified column names from the file. These must already be in the dataset.
        Items in colnames but not in the file are read as an empty table

        If update is disabled, only sets the self._data internal variable to allow for a later bulk update
        """
        # prepare data structures
        data_type_dict: Dict[str, MultiPlotWidget.PlotType] = {}  # col header -> plot type IF NOT Default
        data_dict: Dict[str, Tuple[np.typing.ArrayLike, np.typing.ArrayLike]] = {}  # col header -> xs, ys
        csv_data_items_dict: Dict[str, Set[str]] = {}
        if append:
            data_type_dict.update(self._data_items)
            data_dict.update(self._data)
            csv_data_items_dict.update(self._csv_data_items)

        if colnames is not None:  # clear colnames data, if specified
            for data_name in colnames:
                data_dict[data_name] = (np.array([]), np.array([]))
                assert data_name in data_type_dict  # keeps prior value

        # read through CSVs
        any_is_timevalue = False
        for csv_filepath in csv_filepaths:
            df = pd.read_csv(csv_filepath)
            self._csv_time[csv_filepath] = time.time()

            time_values = df[df.columns[0]]
            assert pd.api.types.is_numeric_dtype(time_values)

            for col_name, dtype in zip(df.columns[1:], df.dtypes[1:]):
                csv_data_items_dict.setdefault(csv_filepath, set()).add(col_name)

                values = df[col_name]
                if pd.api.types.is_numeric_dtype(values):  # is numeric
                    data_type = MultiPlotWidget.PlotType.DEFAULT
                else:  # assume string
                    data_type = MultiPlotWidget.PlotType.ENUM_WAVEFORM
                data_type_dict[col_name] = data_type

                not_nans = pd.notna(values)
                if not_nans.all():
                    xs = time_values
                    ys = values
                else:  # get rid of nans
                    xs = time_values[not_nans]
                    ys = values[not_nans]
                data_dict[col_name] = (xs, ys)

                # if not in append mode, check if a time axis is needed - inferring by if min is Jan 1 2000 in timestamp
                if not append and min(cast(Sequence[int], time_values)) >= 946684800:
                    any_is_timevalue = True

        if any_is_timevalue:
            self._plots.set_x_axis(lambda: TimeAxisItem(orientation="bottom"))

        if colnames is None:  # colnames not None means update only
            data_items = [(name, int_color(i), data_type) for i, (name, data_type) in enumerate(data_type_dict.items())]
            self._set_data_items(data_items)

        self._data_items = data_type_dict
        self._data = data_dict
        self._csv_data_items = csv_data_items_dict
        if update:
            self._set_data(data_dict)

        return self

    def _on_save_config(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(None, "Save config", filter="YAML files (*.yml)")
        if not filename:  # nothing selected, user canceled
            return
        model = self._do_save_config(filename)
        with open(filename, "w") as f:
            f.write(yaml.dump(model.model_dump(), sort_keys=False))

    def _do_save_config(self, filename: str) -> CsvLoaderStateModel:
        model = self._dump_data_model(self._plots._data_items.keys())
        assert isinstance(model, CsvLoaderStateModel)

        if len(self._csv_data_items) == 0:
            model.csv_files = []
        else:
            # this is a bit of a hack, CSV names should be in _write_model
            # but we need access to the filename to determine if writing relpath or abspath
            csvs_commonpath = os.path.commonpath(self._csv_data_items.keys())

            config_dir = os.path.dirname(filename)
            try:
                all_commonpath = os.path.commonpath([csvs_commonpath, config_dir])
            except ValueError:  # eg, paths not on same drive
                all_commonpath = None
            # TODO there should be some indication to the user about whether it's saving
            # in relpath or abspath mode, probably in the file dialog, and an explanation of why it matters
            if all_commonpath is not None and os.path.abspath(config_dir) == os.path.abspath(all_commonpath):
                # save as relpath, configs above CSVs
                model.csv_files = [
                    os.path.relpath(csv_filename, config_dir) for csv_filename in self._csv_data_items.keys()
                ]
            else:  # save as abspath, would need .. access to get CSVs
                model.csv_files = [os.path.abspath(csv_filename) for csv_filename in self._csv_data_items.keys()]

        self._loaded_config_abspath = os.path.abspath(filename)
        self._append_recent()

        return model

    def _on_load_config(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(None, "Load config", filter="YAML files (*.yml)")
        if not filename:  # nothing selected, user canceled
            return
        self.load_config_file(filename)

    def load_config_file(self, filename: str) -> None:
        skeleton_model_type = self._create_skeleton_model_type()
        with open(filename, "r") as f:
            model = skeleton_model_type.model_validate(skeleton_model_type(**yaml.load(f, Loader=TupleSafeLoader)))
        assert isinstance(model, CsvLoaderStateModel)
        self._do_load_config(filename, model)

    def _do_load_config(self, filename: str, model: CsvLoaderStateModel) -> None:
        if model.csv_files is not None:
            missing_csv_files = []
            found_csv_files = []
            for csv_file in model.csv_files:
                if not os.path.isabs(csv_file):  # append yml path to relpaths
                    csv_file = os.path.join(os.path.dirname(filename), csv_file)
                if os.path.exists(csv_file):
                    found_csv_files.append(csv_file)
                else:
                    missing_csv_files.append(csv_file)
            if missing_csv_files:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Some CSV files not found: {', '.join(missing_csv_files)}",
                    QMessageBox.StandardButton.Ok,
                )
            self._load_csvs(found_csv_files, update=False)

        data = self._data
        self._set_data({})  # blank the data while updates happen, for performance
        self._load_model(model)
        assert isinstance(self._table, StatsSignalsTable)
        self._disable_stats_action.setChecked(self._table.stats_disabled())

        # force-update data items and data
        data_items = [(name, int_color(i), data_type) for i, (name, data_type) in enumerate(self._data_items.items())]
        self._set_data_items(data_items)
        self._set_data(data)  # bulk update everything for performance
        self._loaded_config_abspath = os.path.abspath(filename)
        self._append_recent()
