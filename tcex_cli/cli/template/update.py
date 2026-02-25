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
        None, '--template', help='Only provide this value if changing the saved value.'
    ),
    template_type: StrOrNone = typer.Option(None, '--type', help='The App type being initialized.'),
    clear: bool = typer.Option(
        default=False, help='Clear stored template cache in ~/.tcex/ directory.'
    ),
    force: bool = typer.Option(
        default=False, help="Update files from template even if they haven't changed."
    ),
    branch: str = typer.Option(
        default_branch, help='The git branch of the tcex-app-template repository to use.'
    ),
    app_builder: bool = typer.Option(
        default=False, help='Include .appbuilderconfig file in template download.'
    ),
    proxy_host: StrOrNone = typer.Option(None, help='(Advanced) Hostname for the proxy server.'),
    proxy_port: IntOrNone = typer.Option(None, help='(Advanced) Port number for the proxy server.'),
    proxy_user: StrOrNone = typer.Option(None, help='(Advanced) Username for the proxy server.'),
    proxy_pass: StrOrNone = typer.Option(None, help='(Advanced) Password for the proxy server.'),
):
    r"""Update a project with the latest template files.

    Templates can be found at: https://github.com/ThreatConnect-Inc/tcex-app-templates

    The template name will be pulled from tcex.json by default. If the template option
    is provided it will be used instead of the value in the tcex.json file. The tcex.json
    file will also be updated with new values.

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

    if clear:
        cli.clear_cache(branch)

    try:
        # pass raw CLI args — TemplateCli.update() resolves None from tcex.json
        cli.update(branch, template_name, template_type, force, app_builder)

        # read the resolved values (loaded by update() from tcex.json)
        resolved_name = cli.app.tj.model.template_name
        resolved_type = cli.app.tj.model.template_type

        # only persist to tcex.json when user explicitly changed template/type
        if template_name is not None or template_type is not None:
            cli.update_tcex_json(resolved_name, resolved_type)

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
