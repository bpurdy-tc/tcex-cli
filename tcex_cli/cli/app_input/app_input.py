"""TcEx Framework Module"""

# third-party
import typer

# first-party
from tcex_cli.cli.app_input.app_input_cli import AppInputCli
from tcex_cli.render.render import Render


def command(
    name: str = typer.Option(
        ..., '--name', help='Config file name (written under app_inputs.d/).', prompt=True
    ),
    description: str = typer.Option(
        ..., '--description', help='Human-readable description of this config.', prompt=True
    ),
    include_optional: bool = typer.Option(
        default=False, help='If true optional parameters will be included.'
    ),
):
    """Build an app_inputs.d/ config file from the app's install.json file."""
    cli = AppInputCli(name, description, include_optional)
    try:
        # generate app_inputs.json
        cli.generate_app_inputs()

        Render.panel.success('Completed successfully.')
    except Exception as ex:
        cli.log.exception('Failed to run "tcex deps" command.')
        Render.panel.failure(f'Exception: {ex}')
