"""TcEx Framework Module"""

from tcex_cli.app.config import AppSpecYml
from tcex_cli.app.config.model import LayoutJsonModel
from tcex_cli.cli.cli_abc import CliABC


class GenLayoutJson(CliABC):
    """Generate App Config File"""

    def __init__(self, asy: AppSpecYml):
        """Initialize instance properties."""
        super().__init__()
        self.asy = asy

        # properties
        self.filename = 'layout.json'

    def generate(self):
        """Generate the layout.json file data."""

        layout_json_data = {
            'inputs': self.asy.model.inputs,
            'outputs': self.asy.model.outputs,
        }
        # outputs is a list[dict]; Pydantic coerces the dicts into OutputsModel at construction.
        return LayoutJsonModel(**layout_json_data)  # ty: ignore[invalid-argument-type]
