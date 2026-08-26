"""TcEx Framework Module"""

from pydantic import BaseModel

from tcex_cli.cli.run.model.common_model import CommonModel


class InputsModel(CommonModel, extra='allow'):
    """InputsModel"""


class StageModel(BaseModel):
    """Model Definition"""

    kvstore: dict[str, str | dict | list[str | dict]] = {}


class CommonAppInputModel(BaseModel):
    """Model Definition"""

    description: str | None = None
    stage: StageModel
    trigger_inputs: list[dict] = []
    inputs: InputsModel
