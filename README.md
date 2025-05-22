# pyqtgraph-scope-plots
[![PyPI Latest Release](https://img.shields.io/pypi/v/pyqtgraph-scope-plots.svg)](https://pypi.org/project/pyqtgraph-scope-plots/)
![Unit Tests](https://github.com/enphase/pyqtgraph-scope-plots/actions/workflows/python-app.yml/badge.svg?branch=main)

High-performance, feature-rich, and interactive oscilloscope-like plot widgets built in [PyQtGraph](https://github.com/pyqtgraph/pyqtgraph).
Designed with electrical and digital waveforms in mind, but generalizes to any timeseries data.


## Example
This is primarily a widget library for those needing interactive plotting tools, but does include an example CSV viewer.

![example.png](docs/example.png)

Once this package is installed, the [example viewer](pyqtgraph_scope_plots/csv/csv_plots.py) can be started with
```shell
python -m pyqtgraph_scope_plots.csv
```

This starts with some default data (a sine wave, square wave, enum, and steps) but CSVs can be loaded through the interface.
CSVs must have time on the first column and arbitrary data (numeric or strings) on other columns.
Additional data from different CSV files can be appended, which will be interpreted as new columns.

All the features listed below are available.


## Features
- High performance using pyqtgraph, interactive navigation up to millions of points.
- Snap-to-nearest point on hover (if zoomed in far enough).
- Show numeric values of hovered points at the same time.
- Select regions over time (created by double-clicking on the plot).
- Points-of-interest, persistent markers on the plot showing numeric values (created by shift+double-clicking on the plot).
- Statistics (min / max / average / RMS / standard deviation), over the selected region or entire data.
- Drag-and-drop from table to plot to overlay and re-order plots.
- Apply transformation functions, written as Python code (using [simpleeval](https://github.com/danthedeckie/simpleeval)), to signals (using the right-click menu on the signals table).
- Apply time-shift to signals (using the right-click menu on the signals table).


## Architecture
This library makes heavy use of mixins to split out functionality into mostly-independent classes. 

- `PlotItem` Interactivity Mixins: these can be mixed in to a custom `PlotItem` to add interactivity:
    - `SnappableHoverPlot`: snaps to the data point nearest the cursor, providing a visual target.
      The snapped point is also available for tools to build upon.
    - `LiveCursorPlot`: provides a vertical line over the mouse cursor, that shows the values of all intersecting points.
      Uses the snapping function to snap to the nearest data point.
    - `RegionPlot`: provides a user-defined region (via double-click) that shows the x-axis distance between the cursors.
      The region data is also available for tools to build upon.
    - `PointsOfInterestPlot`: allows users to add arbitrarily many points of interest (vertical lines) that shows the values of all intersecting points.
    - `DraggableCursorPlot`: allows a programmatically-initiated draggable cursor that fires a qt-signal when moved. 
      Used as infrastructure to support time shifting signals. 
- `EnumWaveformPlot`: a `PlotItem` that renders string-valued data as a waveform.
- `MultiPlotWidget`: a `QSplitter` widget with multiple plots stacked vertically, with a common x-axis.
  These mixin classes are provided to add functionality:
    - `LinkedMultiPlotWidget`: links the live cursor, region, and points of interest (from interactivity mixins) between plots.
    - `DroppableMultiPlotWidget`: allows an externally-initiated drag-and-drop operation to reorganize (rearranging and combining / overlaying) plots.
- `SignalsTable`: `QTableWidget` that lists signals and provides an extensible base for additional columns.
  These mixin classes are provided to add functionality:
    - `StatsSignalsTable`: adds stats (like min, max, avg) per-signal, optionally over a selected x-range.
    - `DeleteableSignalsTable`: adds delete-signal functionality that fires a qt-signal (and does nothing else - deletion must be handled externally).
    - `TransformsSignalTable`: allows the user to set a function (using a subset of Python) on signals to transform the input data.
      This function has access to the x (as `t`) and y (as `x`) values of the current point as well as other signals at the same index (as `data`).
    - `TimeshiftSignalTable`: allows the user to shift signals in time, in coordination with `DraggableCursorPlot`.
    - `DraggableSignalsTable`: enables initiating a drag-and-drop operation, to be dropped into some external widget.
- `PlotsTableWidget`: combines `MultiPlotWidget` and `SignalsTable` (with all their mixins), linked with each other, into a `QSplitter`.
    - Provides an extension point for an optional widget on the bottom right through `_init_controls`, for example to add a controls box.
    - The data items are first initialized with `_set_data_items` (with name, color, and plot-type of each data item), then data can be updated with `_set_data` (as a name-to-(xs, ys) mapping).
