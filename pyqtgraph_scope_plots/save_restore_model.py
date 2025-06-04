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


class DataTopModel(BaseModel):
    # note, fields dynamically set by HasSaveRestoreModel._get_model_bases
    pass


class BaseTopModel(BaseModel):
    data: Dict[str, DataTopModel]
    # note, fields dynamically set by HasSaveRestoreModel._get_model_bases


class HasSaveRestoreModel:
    """Mixin class to table and multiplotwidget that defines functionality
    to save the GUI state to a Pydantic model and by extension JSON.

    The model is broken down into two sections: data (keyed by data name, sorted by data order,
    contains per-data items like timeshift and transforms), and misc (which contains everything else,
    typically UI state like regions and X-Y plot configurations).

    Each subclass of this (typically a mixin into table or multiplotwidget) defines BaseModel
    mixins into both data and misc, a save function for model (including the data), and
    a load function for model (including the data).
    """

    def _get_model_bases(
        self, data_bases: List[Type[BaseModel]], misc_bases: List[Type[BaseModel]]
    ) -> Tuple[List[Type[BaseModel]], List[Type[BaseModel]]]:
        """Returns the (data bases, misc bases) of this. Typically implemented as a concat of the incoming types.

        IMPLEMENT ME."""
        return data_bases, misc_bases

    def _create_skeleton_model(self, data_names: Iterable[str]) -> BaseTopModel:
        """Returns an empty model of the correct type that can be passed into _save_model."""
        data_bases, model_bases = self._get_model_bases([DataTopModel], [BaseTopModel])
        data_model_cls = pydantic.create_model("DataModel", __base__=tuple(data_bases))
        top_model_cls = pydantic.create_model(
            "TopModel", __base__=tuple(model_bases), data=(Dict[str, data_model_cls], ...)
        )
        top_model = top_model_cls(data={data_name: data_model_cls() for data_name in data_names})  # type: BaseTopModel
        return top_model

    def _save_model(self, model: BaseTopModel) -> None:
        """Saves the data into the top-level model. model.data is pre-populated with models for every data item.
        Mutates the model in-place.

        IMPLEMENT ME."""
        pass

    def _restore_model(self, model: BaseTopModel) -> None:
        """Restores data from the top-level model.

        It is guaranteed that by the time the subclasses of this have the load called, the data_items
        are correctly populated (responsibility of the top-level load). HOWEVER, some data_items
        restores may fail, so this should check for the existence of each data_item.

        TODO: definition for delayed single bulk update

        IMPLEMENT ME."""
        pass
