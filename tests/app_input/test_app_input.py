"""Test Module"""

# standard library
import json
from pathlib import Path
from types import SimpleNamespace

# third-party
import pytest

# first-party
from tcex_cli.cli.app_input.app_input_cli import AppInputCli
from tcex_cli.cli.run.model.common_app_input_model import CommonAppInputModel
from tcex_cli.render.render import Render


def _new_app_input_cli(name: str, description: str = 'desc') -> AppInputCli:
    """Return an AppInputCli instance without running __init__.

    ``AppInputCli.__init__`` loads install.json, which is not needed to exercise the slug /
    write-output logic, so build a bare instance and set only the attributes under test.
    """
    cli = object.__new__(AppInputCli)
    cli.name = name
    cli.description = description
    cli.include_optional = False
    cli.inputs = {}
    cli.kvstore = {}
    # install.json with no params -> generate_app_inputs simply writes the empty config
    cli.ij = SimpleNamespace(model=SimpleNamespace(params=[]))
    return cli


def _answer_yes(*_args, **_kwargs) -> str:
    """Overwrite-prompt stand-in that confirms overwrite."""
    return 'y'


def _answer_no(*_args, **_kwargs) -> str:
    """Overwrite-prompt stand-in that declines overwrite."""
    return 'N'


class TestAppInputSlugify:
    """Test AppInputCli._slugify_name sanitization and anti-traversal guard."""

    @pytest.mark.parametrize(
        argnames='name,expected',
        argvalues=[
            pytest.param('My Config.json', 'my_config', id='pass-spaces-and-json-suffix'),
            pytest.param('my  config', 'my_config', id='pass-collapse-repeats'),
            pytest.param('Smoke-Test_1', 'smoke-test_1', id='pass-allowed-chars'),
            pytest.param('   trim me   ', 'trim_me', id='pass-strip-whitespace'),
            pytest.param('UPPER.JSON', 'upper', id='pass-uppercase-json-suffix'),
        ],
    )
    def test_slugify_valid(self, name: str, expected: str):
        """Valid names slugify to a filesystem-safe lower-case token."""
        cli = _new_app_input_cli(name)
        slug = cli._slugify_name(name)  # noqa: SLF001
        assert slug == expected, f'{name!r} did not slugify to {expected!r}'

    @pytest.mark.parametrize(
        argnames='name,expected',
        argvalues=[
            # traversal/separator characters are stripped to safe single-segment slugs that
            # cannot escape app_inputs.d/ (Path(slug).name == slug holds)
            pytest.param('../x', 'x', id='pass-parent-traversal-sanitized'),
            pytest.param('a/b', 'a_b', id='pass-path-separator-sanitized'),
        ],
    )
    def test_slugify_traversal_sanitized(self, name: str, expected: str):
        """Path-escaping characters are reduced to a safe single-segment slug, not rejected."""
        cli = _new_app_input_cli(name)
        slug = cli._slugify_name(name)  # noqa: SLF001
        assert slug == expected, f'{name!r} did not sanitize to {expected!r}'
        # the resulting slug stays strictly under app_inputs.d/
        assert slug == Path(slug).name

    @pytest.mark.parametrize(
        argnames='name',
        argvalues=[
            pytest.param('', id='fail-empty'),
            pytest.param('   ', id='fail-whitespace-only'),
            pytest.param('***', id='fail-sanitizes-to-empty'),
            pytest.param('.json', id='fail-suffix-only'),
            pytest.param('/', id='fail-separator-only'),
            pytest.param('..', id='fail-dotdot-only'),
        ],
    )
    def test_slugify_rejected(self, name: str):
        """Names that sanitize to empty are rejected via failure (SystemExit)."""
        cli = _new_app_input_cli(name)
        with pytest.raises(SystemExit):
            cli._slugify_name(name)  # noqa: SLF001


class TestAppInputWriteOutput:
    """Test AppInputCli.write_output_file / generate_app_inputs file emission."""

    @staticmethod
    def test_generate_creates_app_inputs_d_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """generate_app_inputs writes app_inputs.d/<slug>.json with description/inputs/stage."""
        monkeypatch.chdir(tmp_path)
        cli = _new_app_input_cli('My Config', description='a smoke test')
        cli.generate_app_inputs()

        output_file = tmp_path / 'app_inputs.d' / 'my_config.json'
        assert output_file.is_file()

        data = json.loads(output_file.read_text(encoding='utf-8'))
        assert data['description'] == 'a smoke test'
        assert data['inputs'] == {}
        assert data['stage']['kvstore'] == {}

    @staticmethod
    def test_write_creates_directory_when_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """write_output_file creates app_inputs.d/ when it does not yet exist."""
        monkeypatch.chdir(tmp_path)
        assert not (tmp_path / 'app_inputs.d').exists()

        cli = _new_app_input_cli('config_one', description='d')
        cli.write_output_file({'description': 'd', 'inputs': {}, 'stage': {'kvstore': {}}})

        assert (tmp_path / 'app_inputs.d' / 'config_one.json').is_file()

    @staticmethod
    def test_overwrite_confirmed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """An existing target + 'y' at the prompt overwrites the file."""
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / 'app_inputs.d'
        config_dir.mkdir()
        target = config_dir / 'existing.json'
        target.write_text(json.dumps({'description': 'old'}), encoding='utf-8')

        monkeypatch.setattr(Render.prompt, 'input', staticmethod(_answer_yes))

        cli = _new_app_input_cli('existing', description='new')
        cli.write_output_file({'description': 'new', 'inputs': {}, 'stage': {'kvstore': {}}})

        data = json.loads(target.read_text(encoding='utf-8'))
        assert data['description'] == 'new'

    @staticmethod
    def test_overwrite_aborted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """An existing target + 'N' at the prompt aborts via failure and leaves the file intact."""
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / 'app_inputs.d'
        config_dir.mkdir()
        target = config_dir / 'existing.json'
        target.write_text(json.dumps({'description': 'old'}), encoding='utf-8')

        monkeypatch.setattr(Render.prompt, 'input', staticmethod(_answer_no))

        cli = _new_app_input_cli('existing', description='new')
        with pytest.raises(SystemExit):
            cli.write_output_file({'description': 'new', 'inputs': {}, 'stage': {'kvstore': {}}})

        # original content is preserved
        data = json.loads(target.read_text(encoding='utf-8'))
        assert data['description'] == 'old'


class TestCommonAppInputModel:
    """Test the description field round-trips and is optional."""

    @staticmethod
    def test_model_with_description():
        """A config WITH a description validates and retains the value."""
        model = CommonAppInputModel(
            description='has description',
            stage={'kvstore': {}},
            inputs={},
        )
        assert model.description == 'has description'

    @staticmethod
    def test_model_without_description_defaults_none():
        """A config WITHOUT a description still validates; description defaults to None."""
        model = CommonAppInputModel(
            stage={'kvstore': {}},
            inputs={},
        )
        assert model.description is None
