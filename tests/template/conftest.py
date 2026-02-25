"""Shared fixtures for template integration tests."""

# standard library
import shutil
import zipfile
from pathlib import Path

# third-party
import pytest

# first-party
from tcex_cli.cli.template.template_cli import TemplateCli

# path to the committed fixture zip
FIXTURE_ZIP = Path(__file__).parent / 'fixtures' / 'tcex-app-templates-v2.zip'


def _extract_fixture_to_cache(cache_dir: Path) -> None:
    """Extract the fixture zip into cache_dir, flattening GitHub's top-level prefix."""
    with zipfile.ZipFile(FIXTURE_ZIP, 'r') as zf:
        names = zf.namelist()
        top_prefix = names[0].split('/', 1)[0]
        zf.extractall(cache_dir)

    # flatten: move contents of top-level prefix dir up
    top_dir = cache_dir / top_prefix
    if top_dir.exists() and top_dir.is_dir():
        for child in top_dir.iterdir():
            target = cache_dir / child.name
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            shutil.move(str(child), str(target))
        shutil.rmtree(top_dir)


@pytest.fixture
def template_cli(tmp_path):
    """Return a TemplateCli with a real extracted template cache.

    The cache is populated from the committed fixture zip so tests
    run offline and deterministically.  Each test gets its own
    tmp_path, so tests are fully isolated.
    """
    tcex_dir = tmp_path / '.tcex'
    tcex_dir.mkdir(parents=True, exist_ok=True)

    cli = TemplateCli(
        proxy_host=None, proxy_port=None, proxy_user=None, proxy_pass=None
    )
    # override the cached_property so _cache_dir uses tmp_path
    cli.__dict__['cli_out_path'] = tcex_dir

    # populate cache from the fixture zip
    cache_dir = cli._cache_dir('v2')
    cache_dir.mkdir(parents=True, exist_ok=True)
    _extract_fixture_to_cache(cache_dir)

    return cli


@pytest.fixture
def project_dir(tmp_path):
    """Return a fresh, empty project directory."""
    d = tmp_path / 'project'
    d.mkdir()
    return d
