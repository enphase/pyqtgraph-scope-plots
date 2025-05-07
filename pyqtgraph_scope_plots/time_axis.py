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

from datetime import datetime
from typing import List, Any

from .interactivity_mixins import DeltaAxisItem


class TimeAxisItem(DeltaAxisItem):
    """Time axis timestamp formatting"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.autoSIPrefix = False  # doesn't make sense for timestamps

    def tickStrings(self, values: List[float], scale: float, spacing: float) -> List[str]:
        out = []
        for value in values:
            try:
                tick_value = datetime.fromtimestamp(value).strftime("%I:%M:%S.%f"[:-3])
            except (OSError, OverflowError):
                tick_value = "🦆"
            out.append(tick_value)
        return out

    def deltaString(self, value: float, scale: float, spacing: float) -> str:
        return super().tickStrings([value], scale, spacing)  # type: ignore
