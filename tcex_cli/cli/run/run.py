"""TcEx Framework Module"""

# standard library
from pathlib import Path

# third-party
import typer

# first-party
from tcex_cli.cli.run.run_cli import RunCli
from tcex_cli.render.render import Render


def command(
    config_json: Path | None = typer.Option(
        None,
        '--config',
        help=(
            'OPTIONAL App Inputs config file. Wins over app_inputs.json and the '
            'app_inputs.d/ menu; pass app_inputs.d/<name>.json to run that file directly.'
        ),
    ),
    debug: bool = typer.Option(default=False, help='Run App in VS Code debug mode.'),
    debug_port: int = typer.Option(
        5678, help='The port to use for the debug server. This must match the launch.json file.'
    ),
):
    """Run the App.

    Configuration & secrets:

    Config resolution precedence: an explicit --config <file> wins and runs that file directly;
    else app_inputs.json if present; else a selection menu over app_inputs.d/*.json. Passing
    --config app_inputs.d/<name>.json runs that scenario without the menu (the unattended path).

    Values come from the local .env (loaded at CLI startup) in two ways: (1) ${env.VAR_NAME}
    placeholders inside the config JSON are substituted from the environment; (2) input model
    fields omitted from the JSON fall back to the environment / .env automatically (the run input
    models are pydantic BaseSettings with env_file='.env', case-insensitive) -- e.g.
    tc_api_access_id, tc_api_secret_key, tc_token, and the proxy and kvstore settings. Values
    present in the JSON take precedence over the .env fallback.

    There is ONE .env at the App root, shared by every file in app_inputs.d/: put credentials
    there once and keep per-scenario inputs in each app_inputs.d/<name>.json. Gotcha: an undefined
    ${env.VAR} is now a hard error -- the run stops and reports which variable to define or fix.
    """
    cli = RunCli()
    try:
        cli.update_system_path()

        # run in debug mode
        if debug is True:
            cli.debug(debug_port)

        # run the App (RunCli.run resolves the config to use)
        cli.run(config_json, debug)

    except Exception as ex:
        cli.log.exception('Failed to run "tcex run" command.')
        Render.panel.failure(f'Exception: {ex}')
