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

from typing import (
    TypeVar,
    Generic,
    Optional,
    Any,
    NamedTuple,
    Tuple,
    Union,
    overload,
    Sequence,
)
from weakref import ref, WeakKeyDictionary, WeakValueDictionary

import numpy as np

PrimaryKeyType = TypeVar("PrimaryKeyType")
ValueType = TypeVar("ValueType")
EntryValueType = TypeVar("EntryValueType")
DefaultType = TypeVar("DefaultType")


class IdentityCacheDict(Generic[PrimaryKeyType, ValueType]):
    """A dict for caching results, where the primary key (eg, input numpy ndarray) is a weak ref (can be unhashable),
    and with optional arguments (both as comparable variables and as weak-referenced identity).
    Keys are compared by identity.
    The cache is hit when the primary key and optional arguments are equal and optional ref_args are identical.
    Cache entries are removed when the primary key is deleted, per WeakKeyDictionary / WeakValueDictionary.

    IMPORTANT - keys are compared by identity. Key objects should be immutable. NumPy arrays are NOT immutable by
    default.

    Based on https://stackoverflow.com/questions/75314250/python-weakkeydictionary-for-unhashable-types
    """

    class Id:
        def __init__(self, key: object) -> None:
            self._id = id(key)
            self._keyref = ref(key)

        def __hash__(self) -> int:
            return self._id

        def __eq__(self, other: object) -> bool:
            return (
                isinstance(other, IdentityCacheDict.Id)
                and self._id == other._id
                and self._keyref() is not None
                and self._keyref() is other._keyref()
            )

    class CacheEntry(NamedTuple):  # note, primary key is stored separately
        args: Any
        ref_args: Tuple[ref[Any], ...]
        value: Any  # should be ValueType

    def __init__(self) -> None:
        self._keys = WeakValueDictionary[
            IdentityCacheDict.Id, PrimaryKeyType
        ]()  # stores the potentially-unhashable keys
        self._values = WeakKeyDictionary[IdentityCacheDict.Id, IdentityCacheDict.CacheEntry]()  # stores the values

    def set(
        self,
        key: PrimaryKeyType,
        args: Any,
        ref_args: Sequence[Any],
        value: ValueType,
    ) -> None:
        if isinstance(key, np.ndarray):
            assert not key.flags.writeable, "NumPy arrays must be immutable to be used as a identity-based key"
        id = self.Id(key)
        self._keys[id] = key
        self._values[id] = self.CacheEntry(args, tuple([ref(ref_arg) for ref_arg in ref_args]), value)

    @overload
    def get(
        self,
        key: PrimaryKeyType,
        args: Any,
        ref_args: Sequence[Any],
        default: None = None,
    ) -> Optional[ValueType]:
        ...

    @overload
    def get(
        self,
        key: PrimaryKeyType,
        args: Any,
        ref_args: Sequence[Any],
        default: DefaultType,
    ) -> Union[ValueType, DefaultType]:
        ...

    def get(
        self,
        key: PrimaryKeyType,
        args: Any,
        ref_args: Sequence[Any],
        default: Any = None,
    ) -> Any:
        id = self.Id(key)
        entry = self._values.get(id, None)
        if entry is None:
            return default
        if args != entry.args:
            return default
        if not (len(ref_args) == len(entry.ref_args)) or not all(
            [ref_arg is entry_arg() for ref_arg, entry_arg in zip(ref_args, entry.ref_args)]
        ):
            return default
        return entry.value
