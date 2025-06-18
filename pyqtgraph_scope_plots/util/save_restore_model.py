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

from typing import List, Type, Dict, Iterable, Optional, Set, TypeVar, Hashable

import pydantic
from pydantic import BaseModel

DedupListType = TypeVar("DedupListType", bound=Hashable)


class HasSaveLoadConfig:
    """Base infrastructure class that allows mixins to each contribute a Pydantic BaseModel fragment
    into a complete BaseModel at the top-level.
    Subclasses define the _MODEL_BASES for its BaseModel fragment, and save and load functionality to/from this model.

    Requirements for models:
    - models must be instantiable with no arguments, fields should have default values

    Recommended conventions for models and save/restore:
    - all fields should be saved with concrete values.
    - fields should be Optional[], where a None means to ignore the field (preserve current value) during loading.
      - this allows users to delete fields from generated files.
    - where a None is a concrete value, use something else, e.g., empty tuple.
    """

    _TOP_MODEL_NAME = "TopModel"
    _MODEL_BASES: List[Type[BaseModel]] = []  # defined in subclasses

    @classmethod
    def _create_class_model_bases(cls) -> Optional[List[Type[BaseModel]]]:
        """Returns the model base fragments for this class only. This is in addition to _MODEL_BASES
        and allows dynamic creation of models."""
        return None

    @classmethod
    def _get_all_model_bases(cls) -> List[Type[BaseModel]]:
        """Returns the model bases of this class, inspecting fragments
        (from both _MODEL_BASES and get_model_fragments) for each superclass.

        Optionally override this if composition is used, for example saving / restore state of children."""
        model_bases = []
        for base in cls.__mro__:
            if issubclass(base, HasSaveLoadConfig) and "_MODEL_BASES" in base.__dict__:
                model_bases.extend(base._MODEL_BASES)
            if issubclass(base, HasSaveLoadConfig) and "_create_class_model_bases" in base.__dict__:
                # call with bottommost subclass
                fn_bases = base._create_class_model_bases.__func__(cls)  # type: ignore
                if fn_bases is not None:
                    model_bases.extend(fn_bases)
        return model_bases

    @staticmethod
    def _deduplicate_list(elts: List[DedupListType]) -> List[DedupListType]:
        seen_elts: Set[DedupListType] = set()
        deduplicated: List[DedupListType] = []
        for elt in elts:
            if elt not in seen_elts:
                deduplicated.append(elt)
                seen_elts.add(elt)
        return deduplicated

    @classmethod
    def _create_skeleton_model_type(cls) -> Type[BaseModel]:
        model_bases = cls._deduplicate_list(cls._get_all_model_bases())
        return pydantic.create_model(cls._TOP_MODEL_NAME, __base__=tuple(model_bases))

    def _dump_model(self) -> BaseModel:
        """For top-level self, generate the save state model. Convenience wrapper around model creation and writing."""
        model = self._create_skeleton_model_type()()
        self._write_model(model)
        return model

    def _write_model(self, model: BaseModel) -> None:
        """Writes data into the top-level model.

        IMPLEMENT ME."""
        pass

    def _load_model(self, model: BaseModel) -> None:
        """Restores data from the top-level model.

        IMPLEMENT ME."""
        pass


class DataTopModel(BaseModel):
    # note, fields dynamically set by HasSaveRestoreModel._get_model_bases
    pass


class BaseTopModel(BaseModel):
    data: Dict[str, DataTopModel]
    # note, fields dynamically set by HasSaveRestoreModel._get_model_bases


class HasSaveLoadDataConfig(HasSaveLoadConfig):
    """Extension of HasSaveLoadConfig, where the model is broken down into two sections:
    data (keyed by data name, sorted by data order, contains per-data items like timeshift and transforms),
    and misc (which contains everything else, typically UI state like regions and X-Y plot configurations).

    Convention-wise, for top-level loading of a plot widget, data_items should be correctly populated
    (by the top-level load) BEFORE subclasses have _load_model called. However, data_items may fail to restore,
    so subclasses should be tolerant of missing dataitems.

    Subclasses should not rely on data values being set. The top-level may blank or lazy-load data values until
    subalssses' state is stored for performance reasons.
    """

    _DATA_MODEL_BASES: List[Type[BaseModel]] = []

    @classmethod
    def _get_data_model_bases(cls) -> List[Type[BaseModel]]:
        model_bases = []
        for base in cls.__mro__:
            if issubclass(base, HasSaveLoadDataConfig) and "_DATA_MODEL_BASES" in base.__dict__:
                model_bases.extend(base._DATA_MODEL_BASES)
        return model_bases

    @classmethod
    def _create_skeleton_model_type(cls) -> Type[BaseModel]:
        model_bases = cls._deduplicate_list(cls._get_all_model_bases() + [BaseTopModel])
        data_model_bases = cls._deduplicate_list(cls._get_data_model_bases() + [DataTopModel])

        data_model_cls = pydantic.create_model("DataModel", __base__=tuple(data_model_bases))
        top_model_cls = pydantic.create_model(
            cls._TOP_MODEL_NAME, __base__=tuple(model_bases), data=(Dict[str, data_model_cls], ...)  # type: ignore
        )
        return top_model_cls

    @classmethod
    def _create_skeleton_data_model(cls, data_names: Iterable[str]) -> BaseTopModel:
        """Returns an empty model of the correct type (containing all _get_model_bases)
        that can be passed into _save_model."""
        top_model_cls = cls._create_skeleton_model_type()
        data_model_cls = top_model_cls.model_fields["data"].annotation.__args__[1]  # type: ignore
        top_model = top_model_cls(data={data_name: data_model_cls() for data_name in data_names})
        return top_model  # type: ignore

    def _dump_data_model(self, data_names: Iterable[str]) -> BaseTopModel:
        """For top-level self, generate the save state model, including top-level data items.
        Convenience wrapper around model creation and writing."""
        model = self._create_skeleton_data_model(data_names)
        self._write_model(model)
        return model
