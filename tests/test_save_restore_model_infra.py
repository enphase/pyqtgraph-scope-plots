from typing import Optional, Type, List, Tuple

from pydantic import BaseModel

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
        self, data_bases: List[Type[BaseModel]], misc_bases: List[Type[BaseModel]]
    ) -> Tuple[List[Type[BaseModel]], List[Type[BaseModel]]]:
        return [DataModelSub1, DataModelSub2] + data_bases, [BaseModelSub1, BaseModelSub2] + misc_bases

    def _save_model(self, model: BaseTopModel) -> None:
        pass

    def _restore_model(self, model: BaseTopModel) -> None:
        pass


def test_save_model() -> None:
    """Tests composition of the save model"""
    instance = SaveRestoreSub()
    skeleton = instance._create_skeleton_model(["data1", "data2", "data3"])

    assert skeleton.data["data1"].field1 == 1
    assert skeleton.data["data1"].field2 is None
    assert skeleton.data["data2"].field1 == 1
    assert skeleton.data["data3"].field1 == 1

    assert skeleton.base_field1 == 4.2
    assert skeleton.inner.a_field == "in"
