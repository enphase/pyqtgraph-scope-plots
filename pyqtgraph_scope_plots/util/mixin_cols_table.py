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

from PySide6.QtWidgets import QTableWidget


class MixinColsTable(QTableWidget):
    """A base class that provides infrastructure for mixins to contribute columns into a QTableWidget"""

    _COL_COUNT: int = -1

    def _pre_cols(self) -> int:  # number of cols before nane
        """Called during beginning of __init__ to calculate column counts.
        Subclasses should override this (with an accumulating super() call) and initialize their offsets.
        """
        return 0

    def _post_cols(self) -> int:  # total number of columns, including _pre_cols
        """Called during beginning of __init__ to calculate column counts.
        Subclasses should override this (with an accumulating super() call) and initialize their offsets.
        """
        return self._COL_COUNT  # base case, starting point

    def _init_col_counts(self) -> None:
        """Called during beginning of init to initialize column offsets and counts. Do NOT override."""
        if self._COL_COUNT < 0:
            self._COL_COUNT = self._pre_cols()
            self._COL_COUNT = self._post_cols()

    def _init_table(self) -> None:
        """Called during init, AFTER _init_col_counts (and where offsets and counts should be valid), to
        do any table initialization like setting up headers.
        Subclasses should override this (including a super() call)"""

    def __init__(self) -> None:
        super().__init__()
        self._init_col_counts()
        self.setColumnCount(self._COL_COUNT)
        self._init_table()
