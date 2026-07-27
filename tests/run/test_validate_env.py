"""Test Module"""

# standard library
import json
from pathlib import Path

# third-party
import pytest

# first-party
from tcex_cli.cli.run.launch_playbook import LaunchPlaybook


def _new_launch_playbook() -> LaunchPlaybook:
    """Return a bare ``LaunchPlaybook`` without running ``__init__``.

    ``LaunchPlaybook.__init__`` (via ``LaunchABC.__init__``) starts a (fake) Redis server and builds
    the input model; ``_validate_env_variables`` needs none of that -- it relies only on
    module-level ``os.getenv`` / ``difflib`` + ``Render``. Build a bare instance so the env-var
    validator can be exercised in isolation.

    Returns:
        A bare ``LaunchPlaybook`` for ``_validate_env_variables`` / ``construct_model_inputs``.
    """
    return object.__new__(LaunchPlaybook)


@pytest.fixture(autouse=True)
def _wide_console(monkeypatch: pytest.MonkeyPatch):
    """Force a very wide rich console so panel text is not wrapped/truncated.

    ``Render.panel.*`` renders through a ``rich`` ``Panel``; rich sizes its console to the terminal
    width (80 cols under pytest capture), which clips the message and makes substring assertions
    flaky. Pinning ``COLUMNS`` keeps the full message on one line for deterministic assertions.
    """
    monkeypatch.setenv('COLUMNS', '4000')


class TestValidateEnvVariables:
    """Test LaunchABC._validate_env_variables fails fast on undefined ${env.NAME} placeholders."""

    @staticmethod
    def test_undefined_env_var_fails(
        capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ):
        """An undefined ${env.NAME} hard-fails (SystemExit) and names the offending var."""
        monkeypatch.delenv('VAULT_MOUNT1', raising=False)
        lp = _new_launch_playbook()
        data = '{"inputs": {"vault_mount": "${env.VAULT_MOUNT1}"}}'

        with pytest.raises(SystemExit):
            lp._validate_env_variables(data)  # noqa: SLF001

        out = capsys.readouterr().out
        assert '${env.VAULT_MOUNT1}' in out

    @staticmethod
    def test_did_you_mean_suggestion(
        capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ):
        """An undefined var with a close-matching defined var is offered as a suggestion."""
        monkeypatch.delenv('VAULT_MOUNT1', raising=False)
        monkeypatch.setenv('VAULT_MOUNT', 'mount-value')
        lp = _new_launch_playbook()
        data = '{"inputs": {"vault_mount": "${env.VAULT_MOUNT1}"}}'

        with pytest.raises(SystemExit):
            lp._validate_env_variables(data)  # noqa: SLF001

        out = capsys.readouterr().out
        # the close-match (defined) var is offered as a suggestion
        assert '${env.VAULT_MOUNT}' in out
        assert 'did you mean' in out.lower()

    @staticmethod
    def test_all_defined_no_error(monkeypatch: pytest.MonkeyPatch):
        """Every referenced env var is defined -> no SystemExit (method returns None)."""
        monkeypatch.setenv('VAULT_MOUNT', 'mount-value')
        lp = _new_launch_playbook()
        data = '{"inputs": {"vault_mount": "${env.VAULT_MOUNT}"}}'

        # no SystemExit -- all referenced env vars are defined
        assert lp._validate_env_variables(data) is None  # noqa: SLF001

    @staticmethod
    def test_empty_string_env_var_counts_as_defined(monkeypatch: pytest.MonkeyPatch):
        """An env var defined as an empty string is still "defined" -> no SystemExit."""
        monkeypatch.setenv('VAULT_MOUNT', '')
        lp = _new_launch_playbook()
        data = '{"inputs": {"vault_mount": "${env.VAULT_MOUNT}"}}'

        # no SystemExit -- empty-string is a defined value (os.getenv returns '', not None)
        assert lp._validate_env_variables(data) is None  # noqa: SLF001

    @staticmethod
    def test_multiple_undefined_all_reported(
        capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ):
        """Multiple undefined ${env.NAME} placeholders are all named in the failure output."""
        monkeypatch.delenv('A_UNDEF', raising=False)
        monkeypatch.delenv('B_UNDEF', raising=False)
        lp = _new_launch_playbook()
        data = '{"a": "${env.A_UNDEF}", "b": "${env.B_UNDEF}"}'

        with pytest.raises(SystemExit):
            lp._validate_env_variables(data)  # noqa: SLF001

        out = capsys.readouterr().out
        assert '${env.A_UNDEF}' in out
        assert '${env.B_UNDEF}' in out

    @staticmethod
    def test_no_env_tokens_no_error():
        """Plain JSON with no ${env...} placeholders -> no SystemExit."""
        lp = _new_launch_playbook()
        data = '{"inputs": {"vault_mount": "literal-value", "count": 5}}'

        # no SystemExit -- nothing to validate
        assert lp._validate_env_variables(data) is None  # noqa: SLF001


class TestConstructModelInputsEnvValidation:
    """Test construct_model_inputs runs env validation before JSON parsing."""

    @staticmethod
    def test_undefined_env_var_fails_before_json_load(
        capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        """construct_model_inputs hard-fails on an undefined ${env.NAME} before json.loads runs."""
        monkeypatch.delenv('UNDEFINED_X', raising=False)
        config_json = tmp_path / 'app_inputs.json'
        config_json.write_text(
            json.dumps({'inputs': {'vault_mount': '${env.UNDEFINED_X}'}}),
            encoding='utf-8',
        )

        lp = _new_launch_playbook()
        lp.config_json = config_json

        with pytest.raises(SystemExit):
            lp.construct_model_inputs()

        out = capsys.readouterr().out
        assert '${env.UNDEFINED_X}' in out

    @staticmethod
    def test_defined_env_var_substituted_and_parsed(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        """A defined ${env.NAME} passes validation, is substituted, and the JSON parses."""
        monkeypatch.setenv('DEFINED_X', 'secret-mount')
        config_json = tmp_path / 'app_inputs.json'
        config_json.write_text(
            json.dumps({'inputs': {'vault_mount': '${env.DEFINED_X}'}}),
            encoding='utf-8',
        )

        lp = _new_launch_playbook()
        lp.config_json = config_json

        result = lp.construct_model_inputs()
        assert result == {'inputs': {'vault_mount': 'secret-mount'}}
