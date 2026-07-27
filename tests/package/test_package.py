"""Test Module"""

# standard library
from pathlib import Path
from types import SimpleNamespace

# third-party
import pytest

# first-party
from tcex_cli.cli.package.package_cli import PackageCli


def _new_package_cli() -> PackageCli:
    """Return a PackageCli instance without running __init__.

    ``PackageCli.__init__`` only stores ``excludes`` / ``ignore_validation`` / ``output_dir``;
    ``_build_excludes_base`` additionally reads ``self.app.tj.model.package.excludes``. Build a bare
    instance and stub those so the excludes logic can be exercised without loading an App.
    """
    cli = object.__new__(PackageCli)
    cli._excludes = []  # noqa: SLF001
    cli.ignore_validation = False
    cli.output_dir = Path('target')
    cli.app = SimpleNamespace(
        tj=SimpleNamespace(model=SimpleNamespace(package=SimpleNamespace(excludes=[])))
    )
    return cli


class TestPackageExcludes:
    """Test that app_inputs.d/ is excluded from packaging."""

    @staticmethod
    def test_app_inputs_d_in_base_excludes():
        """_build_excludes_base contains the bare 'app_inputs.d' token (a directory, not a glob)."""
        cli = _new_package_cli()
        excludes = cli._build_excludes_base  # noqa: SLF001
        assert 'app_inputs.d' in excludes
        # bare token, not a glob (a glob would only drop the contents, leaving an empty dir)
        assert 'app_inputs.d/**' not in excludes

    @staticmethod
    def test_exclude_files_ignores_app_inputs_d(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """exclude_files() flags an 'app_inputs.d' directory entry for exclusion."""
        monkeypatch.chdir(tmp_path)
        cli = _new_package_cli()

        names = ['app.py', 'app_inputs.d', 'install.json']
        ignored = cli.exclude_files(str(tmp_path), names)
        assert 'app_inputs.d' in ignored
        # a normal source file is not excluded
        assert 'app.py' not in ignored
