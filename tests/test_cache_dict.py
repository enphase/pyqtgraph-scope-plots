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

import numpy as np
import numpy.typing as npt

from pyqtgraph_scope_plots.util.cache_dict import IdentityCacheDict


def test_cache_dict() -> None:
    cd = IdentityCacheDict[npt.NDArray[np.float64], npt.NDArray[np.float64]]()
    arr1 = np.array([1, 2, 3, 4])
    arr1.flags.writeable = False
    arr1b = np.array([2, 3, 4, 5])
    arr2 = np.array([4, 3, 2, 1])

    # test basic set and get keys
    cd.set(arr1, None, [], arr1b)
    assert cd.get(arr1, None, []) is arr1b
    assert cd.get(arr2, None, []) is None

    # test args
    assert cd.get(arr1, ("ducks"), []) is None
    cd.set(arr1, ("ducks"), [], arr1b)
    assert cd.get(arr1, ("ducks"), []) is arr1b
    assert cd.get(arr1, ("no"), []) is None
    assert cd.get(arr1, None, []) is None

    # test weak ref args
    assert cd.get(arr1, ("ducks"), [arr2]) is None
    cd.set(arr1, ("ducks"), [arr2], arr1b)
    assert cd.get(arr1, ("ducks"), [arr2]) is arr1b
    assert cd.get(arr1, ("ducks"), []) is None
