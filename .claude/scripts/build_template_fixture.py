#!/usr/bin/env python3
"""Regenerate the pytest template fixture zip as a GitHub-style archive.

The fixture consumed by ``tests/template/conftest.py::_extract_fixture_to_cache`` must be a
GitHub-style archive: every entry lives under a SINGLE top-level wrapper directory (e.g.
``tcex-app-templates-2/``). conftest computes ``top_prefix = names[0].split('/', 1)[0]`` and strips
that one wrapper. If the zip is packaged WITHOUT a wrapper, the flatten step destroys top-level dirs
like ``_app_common`` and breaks the template tests.

This script rebuilds the zip from the git-tracked files of the source templates repo (mimicking a
GitHub archive) and nests every entry under ``--prefix``.
"""

from __future__ import annotations

# standard library
import io
import subprocess  # nosec B404 — used only with static list args, shell=False
import zipfile
from pathlib import Path

# third-party
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

DEFAULT_SOURCE = Path(
    '/Users/bsummers/WorkBench/010__DEVELOPMENT/SDK/tcex-packages/tcex-app-templates'
)
DEFAULT_OUTPUT = Path(
    '/Users/bsummers/WorkBench/010__DEVELOPMENT/SDK/tcex-packages/tcex-cli-1.0'
    '/tests/template/fixtures/tcex-app-templates-v2.zip'
)
DEFAULT_PREFIX = 'tcex-app-templates-2'

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()


def _fail(message: str) -> None:
    """Print a loud error and exit non-zero."""
    console.print(Panel(message, title='[bold red]error[/]', border_style='red'))
    raise typer.Exit(code=1)


def _tracked_files(source: Path) -> list[str]:
    """Return the sorted, git-tracked file paths of the source repo (forward-slash, relative)."""
    # B603 — static argv, shell=False, no user-controlled binary
    result = subprocess.run(  # nosec
        ['git', '-C', str(source), 'ls-files'],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _fail(f'git ls-files failed for {source}:\n{result.stderr.strip()}')
    paths = [line for line in result.stdout.splitlines() if line.strip()]
    return sorted(paths)


def _top_level_after_flatten(paths: list[str]) -> set[str]:
    """Compute the set of top-level entries that survive conftest's wrapper strip.

    The archive entry is ``<prefix>/<path>``; after conftest strips ``<prefix>/`` the remainder is
    ``<path>``, whose first segment is the post-flatten top-level entry.
    """
    return {path.split('/', 1)[0] for path in paths}


@app.command()
def main(
    source: Path = typer.Option(
        DEFAULT_SOURCE,
        '--source',
        help='Source templates repo working tree (read working-tree bytes).',
    ),
    output: Path = typer.Option(
        DEFAULT_OUTPUT, '--output', help='Destination zip path (overwritten on --commit).'
    ),
    prefix: str = typer.Option(
        DEFAULT_PREFIX, '--prefix', help='Single top-level wrapper directory for every entry.'
    ),
    commit: bool = typer.Option(
        False,  # noqa: FBT003 — typer requires the default as a positional value
        '--commit',
        help='Write the zip. Without this flag the script runs read-only (dry-run).',
    ),
) -> None:
    """Build a GitHub-style template fixture zip from git-tracked working-tree files."""
    # 1. validate inputs early.
    if not source.is_dir():
        _fail(f'source is not a directory: {source}')
    if not (source / '.git').exists():
        _fail(f'source does not look like a git repo (no .git): {source}')
    if not prefix or '/' in prefix:
        _fail(f'prefix must be a single non-empty directory name, got: {prefix!r}')

    # 2. gather tracked files (working-tree bytes will be read per-file below).
    paths = _tracked_files(source)
    if not paths:
        _fail(f'no git-tracked files found in {source}')

    # ensure names[0] resolves to a "<prefix>/..." entry (sorted archive names).
    archive_names = sorted(f'{prefix}/{p}' for p in paths)
    first_name = archive_names[0]
    survivors = _top_level_after_flatten(paths)

    # confirm exactly one top-level wrapper exists in the archive (every entry is "<prefix>/...").
    wrapper_segments = {name.split('/', 1)[0] for name in archive_names}
    outside_wrapper = wrapper_segments - {prefix}

    # 3. build the rich summary.
    table = Table(title='template fixture build', show_header=True, header_style='bold cyan')
    table.add_column('field', style='bold')
    table.add_column('value', overflow='fold')
    table.add_row('source', str(source))
    table.add_row('output', str(output))
    table.add_row('prefix (wrapper dir)', prefix)
    table.add_row('tracked file count', str(len(paths)))
    table.add_row('names[0]', first_name)
    table.add_row('archive wrapper segments', ', '.join(sorted(wrapper_segments)))
    table.add_row(
        'top-level entries WILL exist after flatten',
        ', '.join(sorted(survivors)),
    )
    table.add_row(
        'top-level entries OUTSIDE wrapper',
        ', '.join(sorted(outside_wrapper)) if outside_wrapper else '(none — single wrapper OK)',
    )
    console.print(table)

    if outside_wrapper:
        _fail(
            'archive would contain entries outside the single wrapper directory: '
            f'{sorted(outside_wrapper)}'
        )

    # 4. dry-run vs commit.
    if not commit:
        console.print(
            '[yellow]dry-run[/] — no zip written (pass --commit to apply). '
            f'Would write {len(paths)} files under {prefix!r} to {output}.'
        )
        return

    # build the archive in memory, then write atomically.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            file_bytes = (source / path).read_bytes()
            zf.writestr(f'{prefix}/{path}', file_bytes)

    output.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output.with_name(output.name + '.tmp')
    tmp_path.write_bytes(buffer.getvalue())
    tmp_path.replace(output)

    size = output.stat().st_size
    console.print(
        Panel(
            f'wrote [bold]{len(paths)}[/] files under [bold]{prefix}/[/]\n'
            f'path: {output}\n'
            f'size: {size:,} bytes',
            title='[bold green]committed[/]',
            border_style='green',
        )
    )


if __name__ == '__main__':
    app()
