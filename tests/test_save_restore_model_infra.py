from typing import Optional, Type, List, Tuple

from pydantic import BaseModel
from pydantic._internal._model_construction import ModelMetaclass

from pyqtgraph_scope_plots.save_restore_model import DataTopModel, BaseTopModel, HasSaveRestoreModel


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


class SaveRestoreSub(HasSaveRestoreModel):
    def _get_model_bases(
        self, data_bases: List[ModelMetaclass], misc_bases: List[ModelMetaclass]
    ) -> Tuple[List[ModelMetaclass], List[ModelMetaclass]]:
        data_bases, misc_bases = super()._get_model_bases(data_bases, misc_bases)
        return [DataModelSub1, DataModelSub2] + data_bases, [BaseModelSub1, BaseModelSub2] + misc_bases

    def _save_model(self, model: BaseTopModel) -> None:
        super()._save_model(model)

        assert isinstance(model, BaseModelSub1) and isinstance(model, BaseModelSub2)
        for data_name, data_model in model.data.items():
            assert isinstance(data_model, DataModelSub1) and isinstance(data_model, DataModelSub2)
            data_model.field2 = data_name

        model.base_field1 = 2.0
        model.inner.a_field = "a"

    def _restore_model(self, model: BaseTopModel) -> None:
        super()._restore_model(model)


def test_save_model() -> None:
    """Tests composition of the save model"""
    instance = SaveRestoreSub()
    skeleton = instance._create_skeleton_model(["data1", "data2", "data3"])

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

    instance._save_model(skeleton)
    assert skeleton.base_field1 == 2.0
    assert skeleton.inner.a_field == "a"
    assert skeleton.data["data1"].field2 == "data1"
    assert skeleton.data["data2"].field2 == "data2"
    assert skeleton.data["data3"].field2 == "data3"
