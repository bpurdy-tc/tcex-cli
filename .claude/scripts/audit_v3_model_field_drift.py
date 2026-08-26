#!/usr/bin/env python3
"""Audit drift between the live TC server's v3 OPTIONS /<object>/fields and the generated models.

READ-ONLY: this script only issues OPTIONS/GET requests to the configured ThreatConnect server
(creds/host come from the environment — load your .env before running). It mutates nothing, so the
dry-run/--commit convention does not apply.

For every introspectable v3 object type it compares:
  - server fields:  {f['name'] for f in v3_obj.fields}            (OPTIONS /<object>/fields)
  - model props:    set(v3_obj.properties.keys())                 (OPTIONS /<object>)
and reports server-has / model-lacks drift, mirroring the semantics of the interface test
``TestV3.obj_api_options`` in tests/api/tc/v3/v3_helpers.py (same ``ignore_fields`` and the same
per-object name remappings — the latter surfaced as a note rather than silently dropped).
"""

from __future__ import annotations

# standard library
import inspect
from typing import TYPE_CHECKING

# third-party
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# NOTE: This audit targets the *tcex framework* repo (it depends on the generated v3 models and the
# v3 interface-test helper ``tests.api.tc.v3.v3_helpers.V3Helper``). Those do not exist in this
# tcex_cli repo, which has no v3 API code generator. The import is therefore guarded so a static
# ``ty check`` resolves cleanly here, while running the script in a repo without V3Helper fails
# loudly (see ``_load_v3_helper``). It is a candidate for removal from tcex_cli.
if TYPE_CHECKING:
    # first-party
    from tests.api.tc.v3.v3_helpers import V3Helper  # ty: ignore[unresolved-import]

_V3HELPER_MISSING_MSG = (
    'V3Helper (tests.api.tc.v3.v3_helpers) is not importable. This audit only runs in the tcex '
    'framework repo, which provides the generated v3 models and that test helper; it does not '
    'belong to tcex_cli. Run it from the tcex repo with its .venv and a loaded .env.'
)


def _load_v3_helper() -> type[V3Helper]:
    """Import and return the V3Helper class, failing loudly if it is unavailable.

    V3Helper lives in the tcex framework repo's test suite; this script must be run from there.
    """
    try:
        # first-party
        from tests.api.tc.v3.v3_helpers import (  # noqa: PLC0415  # ty: ignore[unresolved-import]
            V3Helper as _V3Helper,
        )
    except ImportError as ex:  # pragma: no cover - environment guard
        raise RuntimeError(_V3HELPER_MISSING_MSG) from ex
    return _V3Helper


app = typer.Typer(
    add_completion=False,
    help='Audit drift between the live TC v3 schema and the generated v3 models (read-only).',
)
console = Console()
err_console = Console(stderr=True)

# Fields the interface test ignores entirely (never reported as drift).
IGNORE_FIELDS: frozenset[str] = frozenset({'AIsummary'})

# Object types V3Helper knows how to import but that are not simple introspectable objects
# (parent/aggregate modules or non-object helpers). Skipped from the audit.
SKIP_OBJECTS: frozenset[str] = frozenset(
    {
        'batch',
        'case_management',
        'security',
        'threat_intelligence',
        'ti_transform',
        'v3',
    }
)

# Static mirror of the per-object name remappings applied inside TestV3.obj_api_options. A server
# field appearing here is a *known* /fields-vs-/<endpoint> discrepancy the test explicitly handles
# (it maps the server name onto one or more model property names) — it is real drift on the raw
# names, but already accounted for. We surface it as a note so true (unhandled) drift stands out.
KNOWN_REMAPS: dict[str, dict[str, list[str]]] = {
    'exclusion_lists': {
        # 'values' is removed from the comparison entirely.
        'values': [],
    },
    'artifacts': {
        'analytics': [
            'analyticsPriority',
            'analyticsPriorityLevel',
            'analyticsScore',
            'analyticsStatus',
            'analyticsType',
        ],
    },
    'groups': {
        'aliases': ['commonGroup'],
        'common': ['commonGroup'],
        'linkedGroups': ['commonGroup'],
        'references': ['commonGroup'],
        'intelReviews': ['reviews'],
        'userDetails': ['createdBy'],
        'externalDates': ['externalDateAdded', 'externalDateExpires', 'externalLastModified'],
        'sightings': ['firstSeen', 'lastSeen'],
    },
    'indicators': {
        'associationName': ['customAssociationNames'],
        'genericCustomIndicatorValues': ['value1', 'value2', 'value3'],
        'threatAssess': [
            'threatAssessConfidence',
            'threatAssessRating',
            'threatAssessScore',
            'threatAssessScoreFalsePositive',
            'threatAssessScoreObserved',
        ],
        'whoIs': ['whois'],
        'userDetails': ['createdBy'],
        'externalDates': ['externalDateAdded', 'externalDateExpires', 'externalLastModified'],
        'sightings': ['firstSeen', 'lastSeen'],
    },
    'cases': {
        'userDetails': ['createdBy'],
    },
    'intel_requirements': {
        'userDetails': ['createdBy'],
    },
    'results': {
        'intelRequirementDetails': ['intelRequirement'],
        'intelRequirementId': ['intelReqId'],
    },
}


def _candidate_objects() -> list[str]:
    """Return the sorted v3 object types V3Helper can import, minus the skip list."""
    # _module_map keeps its known object types in a static dict inside the staticmethod; reconstruct
    # the candidate set from that source rather than re-listing the names here (keeps them in sync).
    v3_helper = _load_v3_helper()
    source = inspect.getsource(v3_helper._module_map)  # noqa: SLF001 — reuse the test's module map
    names: list[str] = []
    for raw_line in source.splitlines():
        line = raw_line.strip()
        # Keys are written as "'<name>': {" at the top level of the _modules dict.
        if line.endswith("': {") and line.startswith("'"):
            name = line[1 : line.index("'", 1)]
            if name not in SKIP_OBJECTS:
                names.append(name)
    return sorted(set(names))


def _remap_note(obj: str, field: str) -> str:
    """Return a human note if a drifted field is a known-handled remap, else empty string."""
    remaps = KNOWN_REMAPS.get(obj, {})
    if field not in remaps:
        return ''
    targets = remaps[field]
    if not targets:
        return 'known-remapped (dropped from check)'
    return f'known-remapped -> {", ".join(targets)}'


def _audit_object(obj: str) -> dict:
    """Introspect a single v3 object and return its drift record.

    Raises on any introspection failure so the caller can record it as unintrospectable.
    """
    v3_helper = _load_v3_helper()
    helper = v3_helper(obj)
    v3_obj = helper.v3_obj

    server_fields = {f.get('name') for f in v3_obj.fields if f.get('name')}
    model_props = set(v3_obj.properties.keys())

    # drift = server-has, model-lacks, minus globally ignored fields.
    drift = sorted(server_fields - model_props - set(IGNORE_FIELDS))

    return {
        'object': obj,
        'server_count': len(server_fields),
        'model_count': len(model_props),
        'drift': drift,
    }


def _render(records: list[dict], errors: list[tuple[str, str]]) -> None:
    """Render the per-object table, the error table, and the summary panel."""
    table = Table(title='v3 model field drift (server-has / model-lacks)', show_lines=True)
    table.add_column('object', style='cyan', no_wrap=True)
    table.add_column('server fields', justify='right')
    table.add_column('model props', justify='right')
    table.add_column('missing-from-model', style='yellow')
    table.add_column('note', style='dim')

    objects_with_drift = 0
    total_drifted = 0

    for rec in records:
        drift = rec['drift']
        if drift:
            objects_with_drift += 1
            total_drifted += len(drift)
            notes = []
            for field in drift:
                note = _remap_note(rec['object'], field)
                if note:
                    notes.append(f'{field}: {note}')
            missing = '\n'.join(drift)
            note_text = '\n'.join(notes) if notes else ''
            row_style = 'bold'
        else:
            missing = '[green]—[/]'
            note_text = ''
            row_style = ''

        table.add_row(
            rec['object'],
            str(rec['server_count']),
            str(rec['model_count']),
            missing,
            note_text,
            style=row_style,
        )

    console.print(table)

    if errors:
        etable = Table(title='objects that could not be introspected', show_lines=False)
        etable.add_column('object', style='cyan', no_wrap=True)
        etable.add_column('error', style='red')
        for obj, msg in errors:
            etable.add_row(obj, msg)
        console.print(etable)

    summary = (
        f'objects audited: [bold]{len(records)}[/]    '
        f'objects with drift: [bold yellow]{objects_with_drift}[/]    '
        f'total drifted fields: [bold yellow]{total_drifted}[/]    '
        f'unintrospectable: [bold red]{len(errors)}[/]'
    )
    console.print(Panel(summary, title='summary', expand=False))


@app.command()
def main(
    object_: str | None = typer.Option(
        None,
        '--object',
        help="Audit a single v3 object type (e.g. 'groups'). Default: audit all known types.",
    ),
) -> None:
    """Compare the live v3 server schema against the generated models and report field drift."""
    if object_ is not None:
        if object_ in SKIP_OBJECTS:
            err_console.print(
                f"[red]error[/] — '{object_}' is not an introspectable simple object "
                f'(it is in the skip list: {", ".join(sorted(SKIP_OBJECTS))}).'
            )
            raise typer.Exit(code=2)
        # Validate against the known module map.
        if not _load_v3_helper()._module_map(object_):  # noqa: SLF001 — reuse test's module map
            valid = ', '.join(_candidate_objects())
            err_console.print(
                f"[red]error[/] — unknown v3 object '{object_}'. Known objects: {valid}"
            )
            raise typer.Exit(code=2)
        targets = [object_]
    else:
        targets = _candidate_objects()

    if not targets:
        err_console.print('[red]error[/] — no v3 object types to audit.')
        raise typer.Exit(code=2)

    console.print(f'[dim]auditing {len(targets)} object type(s)...[/]')

    records: list[dict] = []
    errors: list[tuple[str, str]] = []
    for obj in targets:
        try:
            records.append(_audit_object(obj))
        except Exception as ex:  # record and continue rather than crash the whole audit
            errors.append((obj, f'{type(ex).__name__}: {ex}'))

    if not records:
        err_console.print('[red]error[/] — no objects could be introspected (check TC creds/host).')
        _render(records, errors)
        raise typer.Exit(code=1)

    _render(records, errors)


if __name__ == '__main__':
    app()
