"""Test Module"""

# standard library
import json
from pathlib import Path

# third-party
import pytest

# first-party
from tcex_cli.cli.run.run_cli import RunCli
from tcex_cli.render.render import Render


def _new_run_cli() -> RunCli:
    """Return a RunCli instance without running __init__.

    ``RunCli.__init__`` validates the cwd is an App directory and loads install.json; none of that
    is needed to exercise ``resolve_config`` / the selection helpers, so build a bare instance.
    """
    return object.__new__(RunCli)


def _write_config(path: Path, description: str = '') -> None:
    """Write a minimal app-inputs config file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({'description': description, 'inputs': {}, 'stage': {'kvstore': {}}}),
        encoding='utf-8',
    )


def _menu_must_not_show(*_args, **_kwargs):
    """Prompt stand-in that fails if the selection menu is ever reached."""
    msg = 'selection menu must not be shown'
    raise AssertionError(msg)


class TestRunCliResolveConfig:
    """Test RunCli.resolve_config precedence and the app_inputs.d/ menu."""

    @staticmethod
    def test_explicit_config_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Explicit --config that exists is returned and skips the menu."""
        monkeypatch.chdir(tmp_path)
        # an app_inputs.json is also present; --config must still win
        _write_config(tmp_path / 'app_inputs.json')
        config = tmp_path / 'custom.json'
        _write_config(config)

        cli = _new_run_cli()
        resolved = cli.resolve_config(config)
        assert resolved == config

    @staticmethod
    def test_explicit_config_in_app_inputs_d_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """An explicit --config pointing inside app_inputs.d/ is returned without a menu."""
        monkeypatch.chdir(tmp_path)
        config = tmp_path / 'app_inputs.d' / 'mytest.json'
        _write_config(config)

        # make the menu fail loudly if it is ever reached
        monkeypatch.setattr(Render.prompt, 'ask', _menu_must_not_show)

        cli = _new_run_cli()
        resolved = cli.resolve_config(Path('app_inputs.d') / 'mytest.json')
        assert resolved == Path('app_inputs.d') / 'mytest.json'

    @staticmethod
    def test_explicit_config_missing_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """An explicit --config that does not exist triggers a failure (SystemExit)."""
        monkeypatch.chdir(tmp_path)
        cli = _new_run_cli()
        with pytest.raises(SystemExit):
            cli.resolve_config(tmp_path / 'does_not_exist.json')

    @staticmethod
    def test_app_inputs_json_used_when_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """With no --config, app_inputs.json is returned and the menu is not shown."""
        monkeypatch.chdir(tmp_path)
        _write_config(tmp_path / 'app_inputs.json')
        monkeypatch.setattr(Render.prompt, 'ask', _menu_must_not_show)

        cli = _new_run_cli()
        resolved = cli.resolve_config(None)
        assert resolved == Path('app_inputs.json')

    @staticmethod
    def test_menu_selects_second_candidate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """No --config / json, multiple app_inputs.d/ files -> menu choice 2 wins."""
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / 'app_inputs.d'
        # create out of lexicographic order to prove sorting drives the indices
        _write_config(config_dir / 'zeta.json', description='zeta config')
        _write_config(config_dir / 'alpha.json', description='alpha config')

        # quiet the table render; capture the choices the prompt is offered
        monkeypatch.setattr(Render, 'table_app_inputs_d', staticmethod(_noop_table))

        captured = {}

        def _ask(_text, choices=None, default=None, **_kwargs):
            captured['choices'] = choices
            captured['default'] = default
            return '2'

        monkeypatch.setattr(Render.prompt, 'ask', _ask)

        cli = _new_run_cli()
        resolved = cli.resolve_config(None)

        # resolve_config uses bare relative Path('app_inputs.d'); sorted -> [alpha.json, zeta.json];
        # choice '2' -> candidates[1] -> zeta.json
        assert resolved == Path('app_inputs.d') / 'zeta.json'
        assert captured['choices'] == ['1', '2']
        assert captured['default'] == '1'

    @staticmethod
    def test_menu_single_candidate_still_shown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """A single app_inputs.d/ file still shows the one-item menu; choice 1 returns it."""
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / 'app_inputs.d'
        _write_config(config_dir / 'only.json', description='only config')

        rendered = {}

        def _table(items):
            rendered['items'] = items

        monkeypatch.setattr(Render, 'table_app_inputs_d', staticmethod(_table))
        monkeypatch.setattr(Render.prompt, 'ask', staticmethod(_answer_one))

        cli = _new_run_cli()
        resolved = cli.resolve_config(None)

        assert resolved == Path('app_inputs.d') / 'only.json'
        # the menu was rendered with exactly one item: (index, stem, description)
        assert rendered['items'] == [(1, 'only', 'only config')]

    @staticmethod
    def test_no_config_available_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Nothing available (no --config, no json, no app_inputs.d/) -> failure (SystemExit)."""
        monkeypatch.chdir(tmp_path)
        cli = _new_run_cli()
        with pytest.raises(SystemExit):
            cli.resolve_config(None)

    @staticmethod
    def test_empty_app_inputs_d_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """An app_inputs.d/ directory with no *.json files -> failure (SystemExit)."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'app_inputs.d').mkdir()
        cli = _new_run_cli()
        with pytest.raises(SystemExit):
            cli.resolve_config(None)


class TestRunCliReadConfigDescription:
    """Test the best-effort raw-JSON description reader used by the menu."""

    @staticmethod
    def test_reads_description(tmp_path: Path):
        """A valid config with a description returns it."""
        config = tmp_path / 'c.json'
        _write_config(config, description='hello world')
        assert RunCli._read_config_description(config) == 'hello world'  # noqa: SLF001

    @staticmethod
    def test_missing_description_returns_blank(tmp_path: Path):
        """A config without a description returns an empty string."""
        config = tmp_path / 'c.json'
        config.write_text(json.dumps({'inputs': {}, 'stage': {'kvstore': {}}}), encoding='utf-8')
        assert RunCli._read_config_description(config) == ''  # noqa: SLF001

    @staticmethod
    def test_invalid_json_returns_blank(tmp_path: Path):
        """Unreadable / invalid JSON never crashes the listing; returns an empty string."""
        config = tmp_path / 'c.json'
        config.write_text('{not valid json', encoding='utf-8')
        assert RunCli._read_config_description(config) == ''  # noqa: SLF001


def _noop_table(_items):
    """No-op stand-in for Render.table_app_inputs_d."""


def _answer_one(*_args, **_kwargs) -> str:
    """Prompt stand-in that selects the first menu item."""
    return '1'
