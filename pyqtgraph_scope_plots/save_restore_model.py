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

from typing import List, Type, Dict, Iterable

import pydantic
from pydantic import BaseModel
from pydantic._internal._model_construction import ModelMetaclass


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

    _MODEL_BASES: List[ModelMetaclass] = []  # defined in subclasses

    @classmethod
    def _get_model_bases(cls) -> List[ModelMetaclass]:
        """Returns the (data bases, misc bases) of this class.
        Inspects each subclasses' TOP_MODEL_BASES and DATA_MODEL_BASES, so no implementation is required
        if all the HasSaveLoadConfig are mixins into the top-level class.

        Optionally override this if composition is used, for example saving / restore state of children."""
        model_bases = []
        for base in cls.__mro__:
            if issubclass(base, HasSaveLoadConfig) and "_MODEL_BASES" in base.__dict__:
                model_bases.extend(base._MODEL_BASES)
        return model_bases

    @classmethod
    def _create_skeleton_model_type(cls) -> Type[BaseModel]:
        model_bases = cls._get_model_bases()
        top_model_cls = pydantic.create_model("TopModel", __base__=tuple(model_bases))  # type: ignore

        return top_model_cls

    def _write_model(self, model: BaseModel) -> None:
        """Saves the data into the top-level model. model.data is pre-populated with models for every data item.
        Mutates the model in-place.

        IMPLEMENT ME."""
        pass

    def _load_model(self, model: BaseModel) -> None:
        """Restores data from the top-level model.

        It is guaranteed that by the time the subclasses of this have the load called, the data_items
        are correctly populated (responsibility of the top-level load). HOWEVER, some data_items
        restores may fail, so this should check for the existence of each data_item.
        data values will not be valid.

        data values will be set after all mixins have completed restore.
        This function does not need to duplicate any work that would otherwise be done on a data value set.

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
    """

    _DATA_MODEL_BASES: List[ModelMetaclass] = []

    @classmethod
    def _get_data_model_bases(cls) -> List[ModelMetaclass]:
        model_bases = []
        for base in cls.__mro__:
            if issubclass(base, HasSaveLoadDataConfig) and "_DATA_MODEL_BASES" in base.__dict__:
                model_bases.extend(base._DATA_MODEL_BASES)
        return model_bases

    @classmethod
    def _create_skeleton_model_type(cls) -> Type[BaseModel]:
        model_bases = cls._get_model_bases()
        data_model_bases = cls._get_data_model_bases()
        model_bases.append(BaseTopModel)
        data_model_bases.append(DataTopModel)

        data_model_cls = pydantic.create_model("DataModel", __base__=tuple(data_model_bases))  # type: ignore
        top_model_cls = pydantic.create_model(
            "TopModel", __base__=tuple(model_bases), data=(Dict[str, data_model_cls], ...)  # type: ignore
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

    def _dump_model(self, data_names: Iterable[str]) -> BaseTopModel:
        """For top-level self, generate the save state model. Convenience wrapper around model creation and writing."""
        model = self._create_skeleton_data_model(data_names)
        self._write_model(model)
        return model
