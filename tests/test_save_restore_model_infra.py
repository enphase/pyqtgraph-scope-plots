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

from typing import Optional, Iterable, cast, Dict, List, Type

from pydantic import BaseModel

from pyqtgraph_scope_plots import DataTopModel, BaseTopModel, HasSaveLoadDataConfig


class DataModelSub1(DataTopModel):
    field1: int = 1


class DataModelSub2(DataTopModel):
    field2: Optional[str] = None


class BaseModelSub1(BaseTopModel):
    base_field1: float = 4.2


class InnerModel(BaseModel):
    a_field: str = "in"


class BaseModelSub2(BaseTopModel):
    inner: InnerModel = InnerModel()


class SaveRestoreSub(HasSaveLoadDataConfig):
    _MODEL_BASES = [BaseModelSub1]

    @classmethod
    def _create_class_model_bases(cls) -> List[Type[BaseModel]]:
        return [BaseModelSub2]

    _DATA_MODEL_BASES = [DataModelSub1, DataModelSub2]

    def __init__(self, data_names: Iterable[str]):
        self.data_field1s = {}
        self.data_field2s: Dict[str, Optional[str]] = {}
        for data_name in data_names:
            self.data_field1s[data_name] = 1
            self.data_field2s[data_name] = data_name

        self.base_field1 = 2.0
        self.inner_a_field = "a"

    def _write_model(self, model: BaseModel) -> None:
        super()._write_model(model)

        assert isinstance(model, BaseModelSub1) and isinstance(model, BaseModelSub2)
        for data_name, data_model in model.data.items():
            assert isinstance(data_model, DataModelSub1) and isinstance(data_model, DataModelSub2)
            data_model.field1 = self.data_field1s[data_name]
            data_model.field2 = self.data_field2s[data_name]

        model.base_field1 = self.base_field1
        model.inner.a_field = self.inner_a_field

    def _load_model(self, model: BaseModel) -> None:
        super()._load_model(model)

        assert isinstance(model, BaseModelSub1) and isinstance(model, BaseModelSub2)
        for data_name, data_model in model.data.items():
            assert isinstance(data_model, DataModelSub1) and isinstance(data_model, DataModelSub2)
            self.data_field1s[data_name] = data_model.field1
            self.data_field2s[data_name] = data_model.field2

        self.base_field1 = model.base_field1
        self.inner_a_field = model.inner.a_field


def test_save_model() -> None:
    """Tests composition of the save model"""
    instance = SaveRestoreSub(["data1", "data2", "data3"])
    skeleton = instance._create_skeleton_data_model(instance.data_field1s.keys())

    assert isinstance(skeleton, BaseModelSub1) and isinstance(skeleton, BaseModelSub2)
    assert isinstance(skeleton.data["data1"], DataModelSub1) and isinstance(skeleton.data["data1"], DataModelSub2)
    assert isinstance(skeleton.data["data2"], DataModelSub1) and isinstance(skeleton.data["data2"], DataModelSub2)
    assert isinstance(skeleton.data["data3"], DataModelSub1) and isinstance(skeleton.data["data3"], DataModelSub2)

    assert skeleton.data["data1"].field1 == 1
    assert skeleton.data["data1"].field2 is None
    assert skeleton.data["data2"].field1 == 1
    assert skeleton.data["data3"].field1 == 1

    assert skeleton.base_field1 == 4.2
    assert skeleton.inner.a_field == "in"

    instance._write_model(skeleton)
    assert skeleton.base_field1 == 2.0
    assert skeleton.inner.a_field == "a"
    assert skeleton.data["data1"].field2 == "data1"
    assert skeleton.data["data2"].field2 == "data2"
    assert skeleton.data["data3"].field2 == "data3"


def test_load_model() -> None:
    instance = SaveRestoreSub(["data1", "data2", "data3"])
    model = instance._create_skeleton_data_model(instance.data_field1s.keys())
    cast(DataModelSub2, model.data["data3"]).field2 = "quack"

    instance._load_model(model)
    assert instance.base_field1 == 4.2
    assert instance.inner_a_field == "in"
    assert instance.data_field2s["data1"] is None  # loaded with default value
    assert instance.data_field2s["data2"] is None
    assert instance.data_field2s["data3"] == "quack"
