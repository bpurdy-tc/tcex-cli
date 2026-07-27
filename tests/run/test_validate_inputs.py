"""Test Module"""

# standard library
from pathlib import Path

# third-party
import pytest

# first-party
from tcex_cli.cli.run.launch_playbook import LaunchPlaybook
from tcex_cli.util import Util


def _new_launch_playbook(config: dict) -> LaunchPlaybook:
    """Return a LaunchPlaybook instance without running ``__init__``.

    ``LaunchPlaybook.__init__`` (via ``LaunchABC.__init__``) starts a (fake) Redis server and builds
    the input model; none of that is needed to exercise ``validate_inputs`` / the variable helpers.
    Build a bare instance and set only the attributes the validator touches: a real ``Util`` (its
    variable parsing is what we exercise), a ``config_json`` path (read for the failure message),
    and a stubbed ``construct_model_inputs`` returning the already-parsed config dict.

    Args:
        config: The parsed config dict ``validate_inputs`` operates on.

    Returns:
        A bare ``LaunchPlaybook`` ready for ``validate_inputs`` / ``_find_app_variables``.
    """
    lp = object.__new__(LaunchPlaybook)
    lp.util = Util()
    lp.config_json = Path('app_inputs.d') / 'mismatch.json'
    lp.construct_model_inputs = lambda: config  # type: ignore[method-assign]
    return lp


@pytest.fixture(autouse=True)
def _wide_console(monkeypatch: pytest.MonkeyPatch):
    """Force a very wide rich console so panel text is not wrapped/truncated.

    ``Render.panel.*`` renders through a ``rich`` ``Panel``; rich sizes its console to the terminal
    width (80 cols under pytest capture), which clips the message and makes substring assertions
    flaky. Pinning ``COLUMNS`` keeps the full message on one line for deterministic assertions.
    """
    monkeypatch.setenv('COLUMNS', '4000')


class TestValidateInputs:
    """Test LaunchPlaybook.validate_inputs cross-checks #App: references against stage.kvstore."""

    @staticmethod
    def test_missing_reference_fails(capsys: pytest.CaptureFixture):
        """An input referencing an unstaged #App: variable hard-fails (SystemExit) before Redis I/O.

        The failure message must name the offending variable and the input that references it.
        """
        config = {
            'inputs': {'vault_mount': '#App:1234:vault_mount!String'},
            'stage': {'kvstore': {'#App:1022:vault_mount!String': 'ninja'}},
        }
        lp = _new_launch_playbook(config)

        with pytest.raises(SystemExit):
            lp.validate_inputs()

        out = capsys.readouterr().out
        assert '#App:1234:vault_mount!String' in out
        assert 'vault_mount' in out

    @staticmethod
    def test_did_you_mean_suggestion(capsys: pytest.CaptureFixture):
        """A staged key with the same key+type but a different job_id is offered as a suggestion."""
        config = {
            'inputs': {'vault_mount': '#App:1234:vault_mount!String'},
            'stage': {'kvstore': {'#App:1022:vault_mount!String': 'ninja'}},
        }
        lp = _new_launch_playbook(config)

        with pytest.raises(SystemExit):
            lp.validate_inputs()

        out = capsys.readouterr().out
        # the suggestion references the staged key (same key+type, different job_id)
        assert '#App:1022:vault_mount!String' in out
        assert 'did you mean' in out.lower()

    @staticmethod
    def test_all_matched_clean(capsys: pytest.CaptureFixture):
        """Every #App: reference is staged -> no error and no unused-key warning."""
        config = {
            'inputs': {'x': '#App:1022:vault_mount!String'},
            'stage': {'kvstore': {'#App:1022:vault_mount!String': 'ninja'}},
        }
        lp = _new_launch_playbook(config)

        # no SystemExit
        lp.validate_inputs()

        out = capsys.readouterr().out
        assert 'not referenced' not in out
        assert 'not staged' not in out

    @staticmethod
    def test_unused_staged_key_warns(capsys: pytest.CaptureFixture):
        """A staged key that no input references -> non-blocking warning, run continues."""
        config = {
            'inputs': {'x': '#App:1022:vault_mount!String'},
            'stage': {
                'kvstore': {
                    '#App:1022:vault_mount!String': 'ninja',
                    '#App:1099:spare!String': 'leftover',
                }
            },
        }
        lp = _new_launch_playbook(config)

        # no SystemExit
        lp.validate_inputs()

        out = capsys.readouterr().out
        assert '#App:1099:spare!String' in out

    @staticmethod
    def test_global_and_trigger_ignored():
        """#Global: / #Trigger: references are runtime-provided and are not validated."""
        config = {
            'inputs': {
                'gbl': '#Global:0:gbl.ts!String',
                'trig': '#Trigger:1:t.body!String',
            },
            'stage': {'kvstore': {}},
        }
        lp = _new_launch_playbook(config)

        # no SystemExit -- non-#App vars are excluded from validation
        lp.validate_inputs()

    @staticmethod
    def test_literal_inputs_ignored():
        """Literal / scalar (non-variable) input values are ignored by the validator."""
        config = {
            'inputs': {'flag': 'true', 'count': 5, 'name': 'plain'},
            'stage': {'kvstore': {}},
        }
        lp = _new_launch_playbook(config)

        # no SystemExit -- no #App: references present
        lp.validate_inputs()

    @staticmethod
    def test_output_variables_excluded(capsys: pytest.CaptureFixture):
        """Amendment 1: tc_playbook_out_variables declares OUTPUT vars -> excluded from the scan.

        The App writes these variables; it does not read them, so their ``#App:...`` values must
        never be required in ``stage.kvstore``. With an empty kvstore there must be no missing-stage
        hard error (no SystemExit) and no missing-variable failure output.
        """
        config = {
            'inputs': {
                'tc_playbook_out_variables': [
                    '#App:1234:out_one!String',
                    '#App:1234:out_two!StringArray',
                ]
            },
            'stage': {'kvstore': {}},
        }
        lp = _new_launch_playbook(config)

        # no SystemExit -- output-variable inputs are excluded from the referenced-variable scan
        lp.validate_inputs()

        out = capsys.readouterr().out
        assert 'not staged' not in out
        assert '#App:1234:out_one!String' not in out
        assert '#App:1234:out_two!StringArray' not in out

    @staticmethod
    def test_output_variables_excluded_but_read_input_still_validated(
        capsys: pytest.CaptureFixture,
    ):
        """A real read input is still validated while output-variable inputs are ignored.

        ``tc_playbook_out_variables`` (an output declaration) is excluded, but a genuine read input
        referencing an unstaged variable still hard-fails. The failure names the read input/variable
        and must NOT name the excluded output variable.
        """
        config = {
            'inputs': {
                'tc_playbook_out_variables': ['#App:1234:out!String'],
                'vault_mount': '#App:1234:vault_mount!String',
            },
            'stage': {'kvstore': {}},
        }
        lp = _new_launch_playbook(config)

        with pytest.raises(SystemExit):
            lp.validate_inputs()

        out = capsys.readouterr().out
        # the genuine read input is flagged
        assert 'vault_mount' in out
        assert '#App:1234:vault_mount!String' in out
        # the excluded output variable is not flagged
        assert '#App:1234:out!String' not in out

    @staticmethod
    def test_output_variables_excluded_no_unused_warning(capsys: pytest.CaptureFixture):
        """Output-variable inputs do not trigger the unused-staged-key warning path.

        Every staged key is referenced by a genuine read input, so even though
        ``tc_playbook_out_variables`` declares its own ``#App:...`` values, there is no
        unused-staged-key warning (and no failure).
        """
        config = {
            'inputs': {
                'tc_playbook_out_variables': ['#App:1234:out!String'],
                'x': '#App:1022:vault_mount!String',
            },
            'stage': {'kvstore': {'#App:1022:vault_mount!String': 'ninja'}},
        }
        lp = _new_launch_playbook(config)

        # no SystemExit
        lp.validate_inputs()

        out = capsys.readouterr().out
        assert 'not referenced' not in out
        assert 'not staged' not in out


class TestFindAppVariables:
    """Test LaunchPlaybook._find_app_variables extracts #App: references from values."""

    @staticmethod
    def test_exact_str():
        """A str that is exactly an #App: variable returns that variable."""
        lp = _new_launch_playbook({})
        assert lp._find_app_variables('#App:1022:vault_mount!String') == {  # noqa: SLF001
            '#App:1022:vault_mount!String'
        }

    @staticmethod
    def test_embedded_str():
        """An #App: variable embedded in surrounding text is still extracted."""
        lp = _new_launch_playbook({})
        value = 'prefix #App:1022:vault_mount!String suffix'
        assert lp._find_app_variables(value) == {  # noqa: SLF001
            '#App:1022:vault_mount!String'
        }

    @staticmethod
    def test_dict_values():
        """#App: references are collected from a dict's values."""
        lp = _new_launch_playbook({})
        value = {
            'a': '#App:1:one!String',
            'b': '#App:2:two!String',
        }
        assert lp._find_app_variables(value) == {  # noqa: SLF001
            '#App:1:one!String',
            '#App:2:two!String',
        }

    @staticmethod
    def test_list_values():
        """#App: references are collected from a list's items."""
        lp = _new_launch_playbook({})
        value = ['#App:1:one!String', '#App:2:two!String']
        assert lp._find_app_variables(value) == {  # noqa: SLF001
            '#App:1:one!String',
            '#App:2:two!String',
        }

    @staticmethod
    @pytest.mark.parametrize(
        argnames='value',
        argvalues=[
            pytest.param(5, id='int'),
            pytest.param(True, id='bool'),
            pytest.param(None, id='none'),
        ],
    )
    def test_scalar_returns_empty(value):
        """Non-str/dict/list scalars yield an empty set."""
        lp = _new_launch_playbook({})
        assert lp._find_app_variables(value) == set()  # noqa: SLF001

    @staticmethod
    @pytest.mark.parametrize(
        argnames='value',
        argvalues=[
            pytest.param('#Global:0:gbl.ts!String', id='global'),
            pytest.param('#Trigger:1:t.body!String', id='trigger'),
        ],
    )
    def test_excludes_global_and_trigger(value):
        """#Global: / #Trigger: variables are excluded (only app_type == 'App' is kept)."""
        lp = _new_launch_playbook({})
        assert lp._find_app_variables(value) == set()  # noqa: SLF001
