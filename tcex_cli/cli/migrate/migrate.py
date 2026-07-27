"""TcEx Framework Module"""

# standard library
from typing import Optional

# third-party
import typer

# first-party
from tcex_cli.cli.migrate.migrate_cli import MigrateCli
from tcex_cli.render.render import Render

# typer does not yet support PEP 604, but pyupgrade will enforce
# PEP 604. this is a temporary workaround until support is added.
IntOrNone = Optional[int]
StrOrNone = Optional[str]


def command(
    forward_ref: bool = typer.Option(
        default=True, help='If true, show typing forward lookup reference that require updates.'
    ),
    apply: bool = typer.Option(
        False,  # noqa: FBT003 - typer requires the default as the first positional arg
        '--apply/--no-apply',
        '--update-code/--no-update-code',
        help=('Write changes to disk. Without it, only a preview is shown (no files modified).'),
    ),
    prompt: bool = typer.Option(
        default=True,
        help=(
            'Confirm each change interactively (only applies with --apply); '
            'use --no-prompt for unattended/agent runs.'
        ),
    ),
):
    """Migrate an App to TcEx 4 from TcEx 2/3.

    Walks every Python file under the current working directory (skipping dependency,
    build, and dot-directories such as deps/, .venv/, and .claude/) and rewrites TcEx
    2/3 imports, method calls, and typing forward references to their TcEx 4 equivalents.

    By default the command only previews the proposed changes and writes nothing. Pass
    --apply (alias --update-code) to write the changes to disk; each change is confirmed
    interactively unless --no-prompt is also given. The unattended/agent path is
    --apply --no-prompt, which applies every change without prompting.
    """
    cli = MigrateCli(
        forward_ref,
        apply,
        prompt,
    )
    try:
        cli.walk_code()
    except Exception as ex:
        cli.log.exception('Failed to run "tcex migrate" command.')
        Render.panel.failure(f'Exception: {ex}')
