"""TcEx Framework Module"""

# standard library
from typing import Any

# first-party
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

        layout_json_data: dict[str, Any] = {
            'inputs': self.asy.model.inputs,
            'outputs': self.asy.model.outputs,
        }
        return LayoutJsonModel(**layout_json_data)
