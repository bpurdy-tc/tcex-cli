"""Regression tests for the renamed-gitignore merged-manifest fix.

`TemplateCli._build_merged_template` renames the template repo's dot-less
``gitignore`` file to ``.gitignore`` for the project.  The template repo ships
BOTH a real ``gitignore`` (the intended project ``.gitignore``) and a stray
dotted ``.gitignore`` recorded in the parent ``manifest.json`` under the
``.gitignore`` key.  The old code looked up the parent manifest by the RENAMED
key (``.gitignore``) and copied that (wrong) entry's sha256 into the merged
manifest, so the manifest described a file that was never written.

The fix computes the merged ``.gitignore`` entry from the file ACTUALLY
WRITTEN: ``sha256`` is hashed from the copied content, ``last_commit`` is reused
from the parent's ``.gitignore`` entry when present (else ``'unknown'``), and
``template_path`` is ``'.gitignore'``.  These tests guard manifest-vs-content
consistency for the renamed gitignore.
"""

# standard library
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

# the 1508-byte real `gitignore` (the intended project .gitignore) content sha
GITIGNORE_CONTENT_SHA = '87cef9c311474dbc9ed4dda3819e936c27a8e67cc131219dcfad7c750c3fabca'
# the 34-byte stray `.gitignore` file's real sha (the wrong-key bug masker)
STRAY_DOTGITIGNORE_SHA = 'd6a587790dc35f19f6ef93b6c69a3ad93bf45525d6b0833cc085fb1ad5569390'


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_merged_manifest(merged_dir: Path) -> dict:
    """Return the merged manifest.json as a dict."""
    return json.loads((merged_dir / 'manifest.json').read_text())


# ==================================================================
# Consistency on the current fixture (baseline)
# ==================================================================
class TestGitignoreMergeConsistency:
    """The merged .gitignore manifest entry agrees with the file written."""

    def test_merged_gitignore_content_is_the_1508_byte_file(self, template_cli):
        """The merged dir .gitignore is the 1508-byte project gitignore (87cef9...)."""
        cache_dir = template_cli._cache_dir('v2')
        merged_dir = template_cli._build_merged_template(cache_dir, 'basic', 'playbook')
        try:
            gitignore = merged_dir / '.gitignore'
            assert gitignore.is_file(), 'merged dir is missing .gitignore'
            assert _sha256_file(gitignore) == GITIGNORE_CONTENT_SHA
        finally:
            # cleanup the caller-owned merged temp dir
            for p in sorted(merged_dir.rglob('*'), reverse=True):
                p.unlink() if p.is_file() else p.rmdir()
            merged_dir.rmdir()

    def test_merged_manifest_sha_matches_written_content(self, template_cli):
        """merged_manifest['.gitignore'].sha256 == sha256 of the written .gitignore."""
        cache_dir = template_cli._cache_dir('v2')
        merged_dir = template_cli._build_merged_template(cache_dir, 'basic', 'playbook')
        try:
            merged_manifest = _read_merged_manifest(merged_dir)
            written_sha = _sha256_file(merged_dir / '.gitignore')

            assert merged_manifest['.gitignore']['sha256'] == written_sha, (
                'merged manifest sha256 disagrees with the .gitignore actually written'
            )
            # and that sha is the 1508-byte content, not the stray 34-byte file
            assert merged_manifest['.gitignore']['sha256'] == GITIGNORE_CONTENT_SHA
        finally:
            for p in sorted(merged_dir.rglob('*'), reverse=True):
                p.unlink() if p.is_file() else p.rmdir()
            merged_dir.rmdir()

    def test_merged_manifest_template_path_is_dotted(self, template_cli):
        """merged_manifest['.gitignore'].template_path == '.gitignore'."""
        cache_dir = template_cli._cache_dir('v2')
        merged_dir = template_cli._build_merged_template(cache_dir, 'basic', 'playbook')
        try:
            merged_manifest = _read_merged_manifest(merged_dir)
            assert merged_manifest['.gitignore']['template_path'] == '.gitignore'
        finally:
            for p in sorted(merged_dir.rglob('*'), reverse=True):
                p.unlink() if p.is_file() else p.rmdir()
            merged_dir.rmdir()

    def test_update_writes_gitignore_to_project(self, template_cli, project_dir, monkeypatch):
        """End-to-end update writes .gitignore (1508-byte content) into the project."""
        monkeypatch.chdir(project_dir)
        with patch.object(template_cli, 'ensure_cache', return_value=template_cli._cache_dir('v2')):
            template_cli.update('v2', 'basic', 'playbook', force=True)

        project_gitignore = project_dir / '.gitignore'
        assert project_gitignore.is_file(), 'update did not write .gitignore to the project'
        assert _sha256_file(project_gitignore) == GITIGNORE_CONTENT_SHA


# ==================================================================
# Guard against the wrong-key regression (the important one)
# ==================================================================
class TestGitignoreMergeWrongKeyRegression:
    """The merged .gitignore sha must come from content, not the stray entry.

    Recreates the real-repo condition where the parent manifest's ``.gitignore``
    key describes the 34-byte stray file.  The old code copied that 34-byte sha
    into the merged manifest (describing a file never written); the fix hashes
    the 1508-byte file actually written.
    """

    @staticmethod
    def _point_manifest_at_stray(cache_dir: Path) -> None:
        """Mutate the in-cache _app_common manifest .gitignore -> 34-byte sha.

        This edits the per-test tmp_path cache copy only — the committed fixture
        zip is never touched.
        """
        manifest_path = cache_dir / '_app_common' / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['.gitignore']['sha256'] = STRAY_DOTGITIGNORE_SHA
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))

    def test_merged_gitignore_sha_ignores_stray_manifest_entry(self, template_cli):
        """Even with the stray sha recorded, the merged entry is the 1508-byte sha."""
        cache_dir = template_cli._cache_dir('v2')

        # sanity: the unmutated fixture currently records the 1508-byte sha (it
        # masks the bug); mutate it to describe the 34-byte stray file instead
        self._point_manifest_at_stray(cache_dir)
        mutated = json.loads((cache_dir / '_app_common' / 'manifest.json').read_text())
        assert mutated['.gitignore']['sha256'] == STRAY_DOTGITIGNORE_SHA

        merged_dir = template_cli._build_merged_template(cache_dir, 'basic', 'playbook')
        try:
            merged_manifest = _read_merged_manifest(merged_dir)
            written_sha = _sha256_file(merged_dir / '.gitignore')

            # fixed code: sha comes from the file actually written (1508-byte)
            assert merged_manifest['.gitignore']['sha256'] == GITIGNORE_CONTENT_SHA, (
                'merged .gitignore sha must be hashed from the written file, '
                'not copied from the stray manifest entry'
            )
            # the old code would copy the 34-byte stray sha — assert it did not
            assert merged_manifest['.gitignore']['sha256'] != STRAY_DOTGITIGNORE_SHA
            # manifest still agrees with the written content
            assert merged_manifest['.gitignore']['sha256'] == written_sha
        finally:
            for p in sorted(merged_dir.rglob('*'), reverse=True):
                p.unlink() if p.is_file() else p.rmdir()
            merged_dir.rmdir()
