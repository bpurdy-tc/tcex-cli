"""TcEx Framework Module"""

import json
import logging
import re
from pathlib import Path

from tcex_cli.app.config.install_json import InstallJson
from tcex_cli.app.config.model.install_json_model import ParamsModel
from tcex_cli.cli.cli_abc import CliABC
from tcex_cli.render.render import Render

# get logger
_logger = logging.getLogger(__name__.split('.', maxsplit=1)[0])


class AppInputCli(CliABC):
    """App Input Handling Module."""

    def __init__(self, name: str, description: str, include_optional: bool = False):
        """Initialize instance properties."""
        super().__init__()

        self.name = name
        self.description = description
        self.include_optional = include_optional
        self.ij = InstallJson()

        # accumulators populated by generate_app_inputs
        self.inputs: dict = {}
        self.kvstore: dict = {}

    @staticmethod
    def get_sample_values(param: ParamsModel, playbook_datatype: str):
        """Get sample values for the variable."""
        sample_data = None

        # Mapping playbookDataType to sample values
        playbook_datatype_map = {
            'Any': 'sampleString',
            'Binary': '<base64 encoded string>',
            'BinaryArray': ['<base64 encoded string>'],
            'KeyValue': {'key': 'sampleKey', 'value': 'sampleValue'},
            'KeyValueArray': [{'key': 'sampleKey', 'value': 'sampleValue'}],
            'String': 'sampleString',
            'StringArray': ['sampleString'],
            'TCEntity': {'id': '123', 'type': 'Address', 'value': '1.1.1.1'},
            'TCEntityArray': [{'id': '123', 'type': 'Address', 'value': '1.1.1.1'}],
        }

        # handle default value for String type
        if param.default is not None and playbook_datatype == 'String':
            sample_data = param.default
        elif param.type == 'Boolean':
            # handle Boolean type
            sample_data = '|'.join(['true', 'false'])
        elif param.type == 'KeyValueList':
            # handle KeyValueList type
            if playbook_datatype in playbook_datatype_map:
                value = playbook_datatype_map[playbook_datatype]
                sample_data = [{'key': 'sampleKey', 'value': value}]
            else:
                panel_msg = f'Unsupported playbookDataType for {param.name}: {playbook_datatype}'
                Render.panel.failure(panel_msg)
        elif playbook_datatype == 'String':
            # handle String type with validValues
            sample_data = '|'.join(param.valid_values) if param.valid_values else 'sampleString'
        elif playbook_datatype in playbook_datatype_map:
            sample_data = playbook_datatype_map[playbook_datatype]
        else:
            panel_msg = f'Unsupported playbookDataType for {param.name}: {playbook_datatype}'
            Render.panel.failure(panel_msg)

        return sample_data

    def prompt_user_for_playbook_datatype(self, param: ParamsModel) -> str:
        """Prompt user for playbookDataType."""
        datatype_choice = Render.prompt.ask(
            'This input has multiple playbookDataTypes, please choose one: ',
            choices=param.playbook_data_type,
            default=param.playbook_data_type[0],
            show_choices=True,
            show_default=True,
        )
        if datatype_choice not in param.playbook_data_type:
            Render.panel.failure(f'Invalid choice: {datatype_choice}. Skipping parameter.')
        return datatype_choice

    def prompt_user_for_optional_params(self, param: ParamsModel) -> bool:
        """Prompt user for whether to include optional parameters."""
        include_optional = Render.prompt.ask(
            f'Include optional parameter "{param.name}": ',
            choices=['y', 'n'],
            default='n',
            show_choices=True,
            show_default=True,
        )
        if include_optional is None:
            return False
        return include_optional == 'y'

    def generate_app_inputs(self):
        """Generate the app_inputs.json file."""
        app_id = '1022'  # static value per instructions
        for param in self.ij.model.params or []:
            Render.panel.info(f'[blue]Processing parameter: {param.name}[/blue]')

            # Handle boolean with a true default value, this makes it required
            if param.type == 'Boolean' and str(param.default).lower() == 'true':
                param.required = True

            # Handle optional parameters
            if param.required is False and not self.include_optional:
                optional_choice = self.prompt_user_for_optional_params(param)
                if optional_choice is False:
                    _logger.info(f'Skipping optional parameter: {param.name}')
                    continue

            # Handle playbookDataType with 'Any'
            if 'Any' in param.playbook_data_type:
                if len(param.playbook_data_type) > 1:
                    Render.panel.warning(
                        f'Parameter {param.name} has multiple playbookDataTypes, but "Any" is '
                        'included. Using "Any" should not be combined with other types.'
                    )
                param.playbook_data_type = [
                    'Binary',
                    'BinaryArray',
                    'KeyValue',
                    'KeyValueArray',
                    'String',
                    'StringArray',
                    'TCEntity',
                    'TCEntityArray',
                ]

            # Handle Choice and MultiChoice types, these params don't take p
            if param.type in ('Choice', 'MultiChoice'):
                param.playbook_data_type = ['String']

            # Handle parameters with no playbookDataType
            if not param.playbook_data_type:
                if param.default:
                    value = param.default
                elif param.valid_values:
                    value = '|'.join(param.valid_values)
                else:
                    value = 'sampleString'
                self.inputs[param.name] = value

                Render.panel.info(
                    f'[green]Added parameter: {param.name} with value: {value}[/green]'
                )
            else:
                # Handle parameters with multiple playbookDataTypes
                if len(param.playbook_data_type) > 1:
                    playbook_datatype = self.prompt_user_for_playbook_datatype(param)
                else:
                    playbook_datatype = param.playbook_data_type[0]

                variable = f'#App:{app_id}:{param.name}!{playbook_datatype}'
                # special handling for KeyValueList
                if param.type == 'KeyValueList':
                    variable = f'#App:{app_id}:{param.name}!KeyValueArray'

                sample_values = self.get_sample_values(param, playbook_datatype)
                self.kvstore[variable] = sample_values
                self.inputs[param.name] = variable
                Render.panel.info(
                    f'[green]Added parameter: {param.name} with variable: {variable}[/green]'
                )

        output = {
            'description': self.description,
            'inputs': self.inputs,
            'stage': {'kvstore': self.kvstore},
        }
        self.write_output_file(output)

    def _slugify_name(self, name: str) -> str:
        """Return a filesystem-safe slug for the config file name.

        The written file must live strictly directly under ``app_inputs.d/``.
        """
        raw = name.strip()
        # drop a trailing ".json" suffix (case-insensitive)
        if raw.lower().endswith('.json'):
            raw = raw[: -len('.json')]

        # lower-case, replace any run of disallowed characters with a single "_"
        slug = re.sub(r'[^a-z0-9_-]+', '_', raw.lower()).strip('_')
        # collapse repeated "_"
        slug = re.sub(r'_+', '_', slug)

        # reject empty or anything that would escape app_inputs.d/
        if not slug or slug != Path(slug).name:
            Render.panel.failure(f'Invalid config file name [{name}].')
        return slug

    def write_output_file(self, output: dict):
        """Write the output to a JSON file under app_inputs.d/."""
        slug = self._slugify_name(self.name)

        # ensure the app_inputs.d/ directory exists
        config_dir = Path('app_inputs.d')
        config_dir.mkdir(parents=True, exist_ok=True)

        output_file = config_dir / f'{slug}.json'
        if output_file.exists():
            overwrite = Render.prompt.input(
                f'{output_file} already exists. Overwrite? (y/N): ',
                prompt_default='N',
                subtitle='File will be overwritten if you enter "y".',
            )
            # ask user if they want to overwrite the file
            if overwrite not in ('y', 'Y', 'yes', 'YES'):
                Render.panel.failure('Aborted. File not overwritten.')
            output_file.unlink()

        # create the app_inputs.d/<slug>.json file
        with output_file.open('w') as f:
            json.dump(output, f, indent=4)
