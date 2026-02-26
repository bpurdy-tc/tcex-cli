"""TcEx Framework Module"""

# standard library
from pathlib import Path
from typing import Optional

# third-party
import typer

# first-party
from tcex_cli.cli.template.template_cli import TemplateCli
from tcex_cli.render.render import Render

# vars
default_branch = 'v2'

# typer does not yet support PEP 604, but pyupgrade will enforce
# PEP 604. this is a temporary workaround until support is added.
IntOrNone = Optional[int]  # noqa: UP007
StrOrNone = Optional[str]  # noqa: UP007


def command(
    template_name: StrOrNone = typer.Option(
        None,
        '--template',
        help='The App template name (only when tcex.json is missing the value).',
    ),
    template_type: StrOrNone = typer.Option(
        None,
        '--type',
        help='The App type (only when tcex.json is missing the value).',
    ),
    clear: bool = typer.Option(
        default=False, help='Clear stored template cache in ~/.tcex/ directory.'
    ),
    force: bool = typer.Option(
        default=False, help="Update files from template even if they haven't changed."
    ),
    branch: str = typer.Option(
        default_branch, help='The git branch of the tcex-app-template repository to use.'
    ),
    proxy_host: StrOrNone = typer.Option(None, help='(Advanced) Hostname for the proxy server.'),
    proxy_port: IntOrNone = typer.Option(None, help='(Advanced) Port number for the proxy server.'),
    proxy_user: StrOrNone = typer.Option(None, help='(Advanced) Username for the proxy server.'),
    proxy_pass: StrOrNone = typer.Option(None, help='(Advanced) Password for the proxy server.'),
):
    r"""Update a project with the latest template files.

    Templates can be found at: https://github.com/ThreatConnect-Inc/tcex-app-templates

    The template name and type are read from the project's tcex.json file.
    Use --template and --type only for legacy projects where tcex.json is
    missing those values.

    Optional environment variables include:\n
    * PROXY_HOST\n
    * PROXY_PORT\n
    * PROXY_USER\n
    * PROXY_PASS\n
    """
    # external Apps do not support update
    if not Path('tcex.json').is_file():
        Render.panel.failure(
            'Update requires a tcex.json file, "external" App templates can not be update.',
        )

    cli = TemplateCli(
        proxy_host,
        proxy_port,
        proxy_user,
        proxy_pass,
    )

    tj_model = cli.app.tj.model

    # If tcex.json already has template_name, --template must NOT be provided.
    if tj_model.template_name is not None and template_name is not None:
        Render.panel.failure(
            'The --template flag cannot be used when template_name is already '
            'set in tcex.json. Remove the flag or clear the value in tcex.json.',
        )

    # If tcex.json already has template_type, --type must NOT be provided.
    if tj_model.template_type is not None and template_type is not None:
        Render.panel.failure(
            'The --type flag cannot be used when template_type is already '
            'set in tcex.json. Remove the flag or clear the value in tcex.json.',
        )

    if clear:
        cli.clear_cache(branch)

    try:
        cli.update(branch, template_name, template_type, force=force)

        # use the resolved values for the summary
        resolved_name = template_name or tj_model.template_name
        resolved_type = template_type or tj_model.template_type

        Render.table.key_value(
            'Update Summary',
            {
                'Template Type': resolved_type,
                'Template Name': resolved_name,
                'Branch': branch,
            },
        )
    except Exception as ex:
        cli.log.exception('Failed to run "tcex update" command.')
        Render.panel.failure(f'Exception: {ex}')
