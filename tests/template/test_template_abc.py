"""Tests for TemplateCli — cache staleness, config reading, parent resolution.

Uses the real committed fixture zip for config/parent tests.
Cache staleness tests still use mocks (they test network behavior).
"""

# standard library
from pathlib import Path
from unittest.mock import patch

# third-party
import pytest

# first-party
from tcex_cli.cli.template.template_cli import TemplateCli


@pytest.fixture
def cli(tmp_path):
    """Return a bare TemplateCli instance with tmp_path as cli_out_path."""
    tcex_dir = tmp_path / '.tcex'
    tcex_dir.mkdir(parents=True, exist_ok=True)
    inst = TemplateCli(
        proxy_host=None, proxy_port=None, proxy_user=None, proxy_pass=None
    )
    inst.__dict__['cli_out_path'] = tcex_dir
    return inst


class CacheHelper:
    @staticmethod
    def create_cache_dir(cli_instance: TemplateCli, branch: str = 'v2') -> Path:
        cache_dir = cli_instance._cache_dir(branch)
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir


# ------------------------------------------------------------------
# Cache directory naming
# ------------------------------------------------------------------
class TestCacheDir:

    def test_path_format(self, cli):
        result = cli._cache_dir('v2')
        assert result == cli.cli_out_path / 'templates' / 'templates-v2'

    def test_different_branches_produce_different_paths(self, cli):
        assert cli._cache_dir('v2') != cli._cache_dir('main')
        assert 'templates-v2' in str(cli._cache_dir('v2'))
        assert 'templates-main' in str(cli._cache_dir('main'))


# ------------------------------------------------------------------
# Cache staleness (mocked — tests network-dependent logic)
# ------------------------------------------------------------------
class TestCacheIsStale:
    """Tests for _cache_is_stale."""

    def test_no_cache_dir_returns_true(self, cli):
        assert cli._cache_is_stale('v2') is True

    def test_fresh_cache_returns_false(self, cli):
        CacheHelper.create_cache_dir(cli)
        with patch.object(cli, '_remote_commit_date', return_value='2020-01-01T00:00:00Z'):
            assert cli._cache_is_stale('v2') is False

    def test_stale_cache_returns_true(self, cli):
        CacheHelper.create_cache_dir(cli)
        with patch.object(cli, '_remote_commit_date', return_value='2099-01-01T00:00:00Z'):
            assert cli._cache_is_stale('v2') is True

    def test_api_failure_returns_false(self, cli):
        CacheHelper.create_cache_dir(cli)
        with patch.object(cli, '_remote_commit_date', return_value=None):
            assert cli._cache_is_stale('v2') is False

    def test_malformed_date_returns_false(self, cli):
        CacheHelper.create_cache_dir(cli)
        with patch.object(cli, '_remote_commit_date', return_value='not-a-date'):
            assert cli._cache_is_stale('v2') is False

    def test_empty_string_date_returns_false(self, cli):
        CacheHelper.create_cache_dir(cli)
        with patch.object(cli, '_remote_commit_date', return_value=''):
            assert cli._cache_is_stale('v2') is False


class TestEnsureCache:
    """Tests for ensure_cache."""

    def test_downloads_when_stale(self, cli):
        with (
            patch.object(cli, '_cache_is_stale', return_value=True),
            patch.object(cli, '_download_and_extract') as mock_dl,
        ):
            cli.ensure_cache('v2')
            mock_dl.assert_called_once_with('v2')

    def test_skips_when_fresh(self, cli):
        with (
            patch.object(cli, '_cache_is_stale', return_value=False),
            patch.object(cli, '_download_and_extract') as mock_dl,
        ):
            cli.ensure_cache('v2')
            mock_dl.assert_not_called()

    def test_returns_cache_dir_path(self, cli):
        with (
            patch.object(cli, '_cache_is_stale', return_value=False),
            patch.object(cli, '_download_and_extract'),
        ):
            result = cli.ensure_cache('v2')
            assert result == cli._cache_dir('v2')


# ------------------------------------------------------------------
# Clear cache
# ------------------------------------------------------------------
class TestClearCache:

    def test_removes_directory(self, cli):
        cache_dir = CacheHelper.create_cache_dir(cli)
        (cache_dir / 'some_file.txt').write_text('data')
        assert cache_dir.exists()

        cli.clear_cache('v2')
        assert not cache_dir.exists()

    def test_nonexistent_directory_is_safe(self, cli):
        assert not cli._cache_dir('v2').exists()
        cli.clear_cache('v2')


# ------------------------------------------------------------------
# Config reading (real fixture data)
# ------------------------------------------------------------------
class TestReadTemplateConfig:
    """Tests for read_template_config against real template data."""

    def test_playbook_basic_config(self, template_cli):
        """Parse playbook/basic template.yaml from the real fixture."""
        cache_dir = template_cli._cache_dir('v2')
        config = template_cli.read_template_config(cache_dir, 'playbook', 'basic')

        assert config is not None
        assert config.name == 'basic'
        assert config.type == 'playbook'
        assert config.contributor == 'ThreatConnect'
        assert '_app_common' in config.template_parents
        assert 'playbook_app.py' in config.template_files
        assert 'run.py' in config.template_files

    def test_organization_basic_config(self, template_cli):
        """Parse organization/basic template.yaml from the real fixture."""
        cache_dir = template_cli._cache_dir('v2')
        config = template_cli.read_template_config(cache_dir, 'organization', 'basic')

        assert config is not None
        assert config.name == 'basic'
        assert config.type == 'organization'
        assert '_app_common' in config.template_parents
        assert 'job_app.py' in config.template_files

    def test_app_common_config(self, template_cli):
        """_app_common uses a different path layout (no type subdirectory)."""
        cache_dir = template_cli._cache_dir('v2')
        config = template_cli.read_template_config(cache_dir, 'playbook', '_app_common')

        assert config is not None
        assert config.name == '_app_common'
        assert '.coveragerc' in config.template_files
        assert 'pyproject.toml' in config.template_files
        assert config.template_parents == []

    def test_missing_template_returns_none(self, template_cli):
        cache_dir = template_cli._cache_dir('v2')
        result = template_cli.read_template_config(cache_dir, 'playbook', 'nonexistent')
        assert result is None

    def test_invalid_yaml_returns_none_and_sets_error(self, template_cli):
        cache_dir = template_cli._cache_dir('v2')
        bad_dir = cache_dir / 'playbook' / 'corrupt_template'
        bad_dir.mkdir(parents=True, exist_ok=True)
        (bad_dir / 'template.yaml').write_text(': : [invalid yaml\n  bad: {')

        result = template_cli.read_template_config(cache_dir, 'playbook', 'corrupt_template')
        assert result is None
        assert template_cli.errors is True

    def test_organization_egress_has_multi_level_parents(self, template_cli):
        cache_dir = template_cli._cache_dir('v2')
        config = template_cli.read_template_config(cache_dir, 'organization', 'egress')

        assert config is not None
        assert config.template_parents == ['_app_common', 'basic']


# ------------------------------------------------------------------
# Parent resolution (real fixture data)
# ------------------------------------------------------------------
class TestResolveTemplateParents:
    """Tests for resolve_template_parents against real template data."""

    def test_playbook_basic_resolves_app_common_first(self, template_cli):
        """playbook/basic has parent _app_common — should resolve [_app_common, basic]."""
        cache_dir = template_cli._cache_dir('v2')
        result = template_cli.resolve_template_parents(cache_dir, 'basic', 'playbook')
        assert result == ['_app_common', 'basic']

    def test_organization_basic_resolves_app_common_first(self, template_cli):
        """organization/basic also has parent _app_common."""
        cache_dir = template_cli._cache_dir('v2')
        result = template_cli.resolve_template_parents(cache_dir, 'basic', 'organization')
        assert result == ['_app_common', 'basic']

    def test_app_common_itself_has_no_parents(self, template_cli):
        """_app_common has no parents — should resolve to just itself."""
        cache_dir = template_cli._cache_dir('v2')
        result = template_cli.resolve_template_parents(cache_dir, '_app_common', 'playbook')
        assert result == ['_app_common']

    def test_three_level_chain(self, template_cli):
        cache_dir = template_cli._cache_dir('v2')
        result = template_cli.resolve_template_parents(cache_dir, 'egress', 'organization')
        assert result == ['_app_common', 'basic', 'egress']

    def test_deduplicates_shared_ancestor(self, template_cli):
        cache_dir = template_cli._cache_dir('v2')
        result = template_cli.resolve_template_parents(cache_dir, 'egress', 'organization')
        assert result.count('_app_common') == 1
