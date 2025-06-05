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

from typing import List, Type, Tuple, Dict, Iterable

import pydantic
from pydantic import BaseModel
from pydantic._internal._model_construction import ModelMetaclass


class DataTopModel(BaseModel):
    # note, fields dynamically set by HasSaveRestoreModel._get_model_bases
    pass


class BaseTopModel(BaseModel):
    data: Dict[str, DataTopModel]
    # note, fields dynamically set by HasSaveRestoreModel._get_model_bases


class HasSaveLoadConfig:
    """Mixin class to table and multiplotwidget that defines functionality
    to save the GUI state to a Pydantic model and by extension JSON.

    The model is broken down into two sections: data (keyed by data name, sorted by data order,
    contains per-data items like timeshift and transforms), and misc (which contains everything else,
    typically UI state like regions and X-Y plot configurations).

    Each subclass of this (typically a mixin into table or multiplotwidget) defines BaseModel
    mixins into both data and misc, a save function for model (including the data), and
    a load function for model (including the data).
    """

    TOP_MODEL_BASES: List[ModelMetaclass] = []  # defined in subclasses
    DATA_MODEL_BASES: List[ModelMetaclass] = []

    @classmethod
    def _get_model_bases(cls) -> Tuple[List[ModelMetaclass], List[ModelMetaclass]]:
        """Returns the (data bases, misc bases) of this class.
        Inspects each subclasses' TOP_MODEL_BASES and DATA_MODEL_BASES, so no implementation is required
        if all the HasSaveLoadConfig are mixins into the top-level class.

        Optionally override this if composition is used, for example saving / restore state of children."""
        top_model_bases = []
        data_model_bases = []
        for base in cls.__mro__:
            if issubclass(base, HasSaveLoadConfig) and "TOP_MODEL_BASES" in base.__dict__:
                top_model_bases.extend(base.TOP_MODEL_BASES)
            if issubclass(base, HasSaveLoadConfig) and "DATA_MODEL_BASES" in base.__dict__:
                data_model_bases.extend(base.DATA_MODEL_BASES)
        return data_model_bases, top_model_bases

    @classmethod
    def _create_skeleton_model_type(cls) -> Tuple[Type[DataTopModel], Type[BaseTopModel]]:
        data_bases, model_bases = cls._get_model_bases()
        data_bases.append(DataTopModel)
        model_bases.append(BaseTopModel)
        data_model_cls = pydantic.create_model("DataModel", __base__=tuple(data_bases))  # type: ignore
        top_model_cls = pydantic.create_model(
            "TopModel", __base__=tuple(model_bases), data=(Dict[str, data_model_cls], ...)  # type: ignore
        )
        return data_model_cls, top_model_cls

    @classmethod
    def _create_skeleton_model(cls, data_names: Iterable[str]) -> BaseTopModel:
        """Returns an empty model of the correct type (containing all _get_model_bases)
        that can be passed into _save_model."""
        data_model_cls, top_model_cls = cls._create_skeleton_model_type()
        top_model = top_model_cls(data={data_name: data_model_cls() for data_name in data_names})
        return top_model

    def _dump_model(self, data_names: Iterable[str]) -> BaseTopModel:
        """For top-level self, generate the save state model. Convenience wrapper around model creation and writing."""
        model = self._create_skeleton_model(data_names)
        self._write_model(model)
        return model

    def _write_model(self, model: BaseTopModel) -> None:
        """Saves the data into the top-level model. model.data is pre-populated with models for every data item.
        Mutates the model in-place.

        IMPLEMENT ME."""
        pass

    def _load_model(self, model: BaseTopModel) -> None:
        """Restores data from the top-level model.

        It is guaranteed that by the time the subclasses of this have the load called, the data_items
        are correctly populated (responsibility of the top-level load). HOWEVER, some data_items
        restores may fail, so this should check for the existence of each data_item.
        data values will not be valid.

        data values will be set after all mixins have completed restore.
        This function does not need to duplicate any work that would otherwise be done on a data value set.

        IMPLEMENT ME."""
        pass
