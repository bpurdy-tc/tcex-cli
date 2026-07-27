"""Tests for the ``tcex migrate`` command (MigrateCli)."""

# the migrate summary counters (_files_scanned / _changes_proposed / _changes_applied /
# _files_changed) are the feature's reporting surface and are asserted directly by these
# tests.
# ruff: noqa: SLF001

# standard library
import contextlib
import io
from pathlib import Path

# third-party
import pytest
from click.testing import Result
from typer.testing import CliRunner

# first-party
from tcex_cli.cli.cli import app
from tcex_cli.cli.migrate.migrate_cli import MigrateCli
from tcex_cli.render.render import Render

# get instance of typer CliRunner for the CLI-layer alias test
runner = CliRunner()

# a known, simple replacement straight from MigrateCli._misc_code_replacements:
#   r'utils = Utils\(\)' -> 'utils = Util()'
REPLACEABLE_LINE = 'utils = Utils()\n'
REPLACED_LINE = 'utils = Util()\n'

# a known import replacement from MigrateCli._tcex_import_replacements:
#   r'from tcex\.utils import Utils' -> 'from tcex.util import Util'
REPLACEABLE_IMPORT = 'from tcex.utils import Utils\n'
REPLACED_IMPORT = 'from tcex.util import Util\n'


def _run_walk(cli: MigrateCli) -> None:
    """Run ``walk_code`` while suppressing the rich console output.

    Args:
        cli: The MigrateCli instance to drive.
    """
    with contextlib.redirect_stdout(io.StringIO()):
        cli.walk_code()


class _PromptRecorder:
    """Record calls to ``Render.prompt.input`` and return a canned response.

    The source accesses ``Render.prompt.input`` as a bare attribute on the
    ``RenderPrompt`` class (no ``cls`` is injected), so this is invoked as a
    plain callable with the positional ``prompt_text`` and the
    ``prompt_default`` keyword.
    """

    def __init__(self, response: str):
        """Initialize instance properties.

        Args:
            response: The value to return from every invocation.
        """
        self.response = response
        self.calls: list[tuple[tuple, dict]] = []

    def __call__(self, prompt_text: str, prompt_default: str = '', **kwargs) -> str:
        """Record the call and return the canned response."""
        self.calls.append(((prompt_text, prompt_default), kwargs))
        return self.response


class _PromptForbidden:
    """Fail if ``Render.prompt.input`` is ever called (non-interactive guard)."""

    def __init__(self):
        """Initialize instance properties."""
        self.calls: list[tuple[tuple, dict]] = []

    def __call__(self, *args, **kwargs) -> str:
        """Record the (unexpected) call so the test can assert it never happens."""
        self.calls.append((args, kwargs))
        return ''


@pytest.mark.run(order=3)
class TestMigrateCli:
    """Tests for MigrateCli skip logic and the preview / apply / prompt paths."""

    @staticmethod
    def _build_tree(root: Path) -> dict[str, Path]:
        """Build a temp tree with skipped reference dirs and a real app.py.

        Args:
            root: The temporary root directory to populate.

        Returns:
            Mapping of logical names to the created file paths.
        """
        # reference file under a nested dot-directory (.claude) -> must be skipped
        claude_ref = root / '.claude' / 'cache' / 'tcex4-ref' / 'tcex' / 'logger' / 'logger.py'
        claude_ref.parent.mkdir(parents=True)
        claude_ref.write_text(REPLACEABLE_LINE, encoding='utf-8')

        # nested dependency directory -> must be skipped
        deps_file = root / 'deps' / 'foo.py'
        deps_file.parent.mkdir(parents=True)
        deps_file.write_text(REPLACEABLE_LINE, encoding='utf-8')

        # nested dot-directory at depth (.venv) -> must be skipped
        venv_file = root / '.venv' / 'lib' / 'bar.py'
        venv_file.parent.mkdir(parents=True)
        venv_file.write_text(REPLACEABLE_LINE, encoding='utf-8')

        # the real app file -> must be walked and rewritten
        app_file = root / 'app.py'
        app_file.write_text(REPLACEABLE_IMPORT + REPLACEABLE_LINE, encoding='utf-8')

        return {
            'claude_ref': claude_ref,
            'deps_file': deps_file,
            'venv_file': venv_file,
            'app_file': app_file,
        }

    def test_walk_code_skips_reference_and_dependency_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Only non-skipped files are walked; only app.py is rewritten on apply.

        Args:
            tmp_path: Pytest temp directory unique to the test.
            monkeypatch: Pytest fixture for changing the working directory.
        """
        files = self._build_tree(tmp_path)
        monkeypatch.chdir(tmp_path)

        # apply + no prompt: writes accepted changes unattended
        cli = MigrateCli(forward_ref=False, apply=True, prompt=False)
        _run_walk(cli)

        # only app.py was scanned (the three skip-dir files were excluded)
        assert cli._files_scanned == 1, f'files_scanned={cli._files_scanned} expected 1'

        # app.py was rewritten with both replacements applied
        assert files['app_file'].read_text(encoding='utf-8') == REPLACED_IMPORT + REPLACED_LINE

        # only app.py was modified on disk
        assert cli._files_changed == 1, f'files_changed={cli._files_changed} expected 1'

        # skipped files are byte-for-byte unchanged
        assert files['claude_ref'].read_text(encoding='utf-8') == REPLACEABLE_LINE
        assert files['deps_file'].read_text(encoding='utf-8') == REPLACEABLE_LINE
        assert files['venv_file'].read_text(encoding='utf-8') == REPLACEABLE_LINE

    @pytest.mark.parametrize(
        argnames='skip_rel_path',
        argvalues=[
            pytest.param(
                # dot-directory reference cache (the original bug)
                '.claude/cache/tcex4-ref/tcex/logger/logger.py',
                id='skip-dot-claude-cache',
            ),
            pytest.param(
                # nested dependency dir at depth
                'src/deps/nested/foo.py',
                id='skip-nested-deps',
            ),
            pytest.param(
                # nested dot-venv at depth
                'pkg/.venv/lib/bar.py',
                id='skip-nested-dot-venv',
            ),
            pytest.param(
                # build/target output dir at depth
                'build/target/out.py',
                id='skip-nested-target',
            ),
            pytest.param(
                # history dir at depth
                'a/.history/old.py',
                id='skip-nested-dot-history',
            ),
        ],
    )
    def test_walk_code_skips_path_at_any_depth(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, skip_rel_path: str
    ):
        """Files whose directory parts include a skip/dot dir are never walked.

        Args:
            tmp_path: Pytest temp directory unique to the test.
            monkeypatch: Pytest fixture for changing the working directory.
            skip_rel_path: Relative path that must be excluded from the walk.
        """
        skip_file = tmp_path / skip_rel_path
        skip_file.parent.mkdir(parents=True)
        skip_file.write_text(REPLACEABLE_LINE, encoding='utf-8')

        # a single walkable file so the walk has something to scan
        app_file = tmp_path / 'app.py'
        app_file.write_text(REPLACEABLE_LINE, encoding='utf-8')

        monkeypatch.chdir(tmp_path)

        # apply + no prompt so the walkable file is actually rewritten
        cli = MigrateCli(forward_ref=False, apply=True, prompt=False)
        _run_walk(cli)

        # only app.py is scanned; the skip path is excluded
        assert cli._files_scanned == 1, f'files_scanned={cli._files_scanned} expected 1'
        assert skip_file.read_text(encoding='utf-8') == REPLACEABLE_LINE
        assert app_file.read_text(encoding='utf-8') == REPLACED_LINE

    def test_walk_code_skips_init_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """``__init__.py`` is in _skip_files and must not be scanned.

        Args:
            tmp_path: Pytest temp directory unique to the test.
            monkeypatch: Pytest fixture for changing the working directory.
        """
        init_file = tmp_path / '__init__.py'
        init_file.write_text(REPLACEABLE_LINE, encoding='utf-8')
        app_file = tmp_path / 'app.py'
        app_file.write_text(REPLACEABLE_LINE, encoding='utf-8')

        monkeypatch.chdir(tmp_path)

        cli = MigrateCli(forward_ref=False, apply=True, prompt=False)
        _run_walk(cli)

        assert cli._files_scanned == 1, f'files_scanned={cli._files_scanned} expected 1'
        assert init_file.read_text(encoding='utf-8') == REPLACEABLE_LINE
        assert app_file.read_text(encoding='utf-8') == REPLACED_LINE

    def test_preview_default_does_not_write_but_counts_proposal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """apply=False previews a change (proposed > 0) but writes nothing.

        Args:
            tmp_path: Pytest temp directory unique to the test.
            monkeypatch: Pytest fixture for changing the working directory.
        """
        app_file = tmp_path / 'app.py'
        app_file.write_text(REPLACEABLE_LINE, encoding='utf-8')

        monkeypatch.chdir(tmp_path)

        # the prompt must never be reached in preview mode
        forbidden = _PromptForbidden()
        monkeypatch.setattr(Render.prompt, 'input', forbidden)

        # apply=False -> preview only; nothing is written and the prompt is never called
        cli = MigrateCli(forward_ref=False, apply=False, prompt=True)
        _run_walk(cli)

        # the file on disk is unchanged
        assert app_file.read_text(encoding='utf-8') == REPLACEABLE_LINE

        # a change was proposed but none applied and no file written
        assert cli._changes_proposed > 0, 'expected a proposed change in preview mode'
        assert cli._changes_applied == 0, f'changes_applied={cli._changes_applied} expected 0'
        assert cli._files_changed == 0, f'files_changed={cli._files_changed} expected 0'
        assert cli._files_scanned == 1, f'files_scanned={cli._files_scanned} expected 1'

        # the interactive prompt is never invoked in preview mode
        assert not forbidden.calls, 'Render.prompt.input must not be called when apply=False'

    def test_apply_no_prompt_writes_without_prompting(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """apply=True, prompt=False applies and writes without calling the prompt.

        Args:
            tmp_path: Pytest temp directory unique to the test.
            monkeypatch: Pytest fixture for changing the working directory.
        """
        app_file = tmp_path / 'app.py'
        app_file.write_text(REPLACEABLE_LINE, encoding='utf-8')

        monkeypatch.chdir(tmp_path)

        # any call to the interactive prompt is recorded so we can assert it never happens
        forbidden = _PromptForbidden()
        monkeypatch.setattr(Render.prompt, 'input', forbidden)

        cli = MigrateCli(forward_ref=False, apply=True, prompt=False)
        _run_walk(cli)

        # the interactive prompt is never invoked when prompt=False
        assert not forbidden.calls, 'Render.prompt.input must not be called when prompt=False'
        assert app_file.read_text(encoding='utf-8') == REPLACED_LINE
        assert cli._files_changed == 1, f'files_changed={cli._files_changed} expected 1'
        assert cli._changes_applied == 1, f'changes_applied={cli._changes_applied} expected 1'

    @pytest.mark.parametrize(
        argnames='response,expect_applied',
        argvalues=[
            pytest.param(
                # explicit yes accepts the change
                'yes',
                True,
                id='accept-yes',
            ),
            pytest.param(
                # the 'y' shorthand also accepts
                'y',
                True,
                id='accept-y',
            ),
            pytest.param(
                # empty input accepts (default is yes)
                '',
                True,
                id='accept-default-empty',
            ),
            pytest.param(
                # 'n' declines the change
                'n',
                False,
                id='decline-n',
            ),
        ],
    )
    def test_apply_prompt_honors_response(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        response: str,
        expect_applied: bool,
    ):
        """apply=True with prompt=True confirms per change; response drives the result.

        Args:
            tmp_path: Pytest temp directory unique to the test.
            monkeypatch: Pytest fixture for changing the working directory.
            response: The canned value returned by the mocked prompt.
            expect_applied: Whether the change is expected to be applied.
        """
        app_file = tmp_path / 'app.py'
        app_file.write_text(REPLACEABLE_LINE, encoding='utf-8')

        monkeypatch.chdir(tmp_path)

        recorder = _PromptRecorder(response)
        monkeypatch.setattr(Render.prompt, 'input', recorder)

        cli = MigrateCli(forward_ref=False, apply=True, prompt=True)
        _run_walk(cli)

        # the interactive prompt was invoked (the whole point of the prompt path)
        assert recorder.calls, 'Render.prompt.input should be called when apply=True, prompt=True'

        if expect_applied:
            assert app_file.read_text(encoding='utf-8') == REPLACED_LINE
            assert cli._files_changed == 1, f'files_changed={cli._files_changed} expected 1'
            assert cli._changes_applied == 1
        else:
            assert app_file.read_text(encoding='utf-8') == REPLACEABLE_LINE
            assert cli._files_changed == 0, f'files_changed={cli._files_changed} expected 0'
            assert cli._changes_applied == 0


@pytest.mark.run(order=3)
class TestMigrateCliAlias:
    """CLI-layer coverage for the ``--update-code`` alias of ``--apply``."""

    @staticmethod
    def _run_command(args: list[str]) -> Result:
        """Invoke the ``tcex`` app command with the given arguments.

        Args:
            args: CLI arguments to pass to the tcex app command.

        Returns:
            The CLI invocation result.
        """
        return runner.invoke(app, args)

    @pytest.mark.parametrize(
        argnames='write_flag',
        argvalues=[
            pytest.param(
                # canonical write switch
                '--apply',
                id='flag-apply',
            ),
            pytest.param(
                # documented alias of --apply
                '--update-code',
                id='flag-update-code',
            ),
        ],
    )
    def test_update_code_alias_writes_like_apply(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        write_flag: str,
    ):
        """``--update-code`` is accepted as an alias of ``--apply`` (both write).

        Args:
            tmp_path: Pytest temp directory unique to the test.
            monkeypatch: Pytest fixture for changing the working directory.
            write_flag: The write-gating flag under test (``--apply`` or alias).
        """
        app_file = tmp_path / 'app.py'
        app_file.write_text(REPLACEABLE_LINE, encoding='utf-8')

        monkeypatch.chdir(tmp_path)

        # --no-prompt for the unattended path; --no-forward-ref to skip the AST pass
        result = self._run_command(
            [
                'migrate',
                write_flag,
                '--no-prompt',
                '--no-forward-ref',
            ]
        )

        assert result.exit_code == 0, result.stdout
        assert app_file.read_text(encoding='utf-8') == REPLACED_LINE
