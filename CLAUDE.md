# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is **TcEx CLI 2.0** (`tcex_cli`) — the command-line tooling for ThreatConnect Exchange Apps. It
is the `tcex` CLI used by App developers to **package, deploy, run, migrate, template, validate, and
generate specs** for ThreatConnect Apps (Playbook, Job, Service, and External Apps). It is a Typer
CLI, not a library/SDK and not a web service — there is no Docker/DB/frontend stack.

> Not to be confused with the **TcEx 4.0** framework (`tcex`, a separate sibling repo). That project
> is the runtime SDK and contains a V3 API code generator. **This project has no code generator and no
> generated code — every file under `tcex_cli/` is hand-maintained.**

- **Language**: Python 3.11+ (`requires-python = ">=3.11"`)
- **CLI framework**: **typer** + **rich**; console entry point `tcex = tcex_cli.cli.cli:app`
- **Models**: Pydantic **v1** (`validator`, `ModelField`, `update_forward_refs`, etc.)
- **Packaging / envs**: managed with **uv** (a `uv` workspace; `uv.lock` + `.venv` at the repo root)
- **Type checker**: **ty** (Astral) — config in root `[tool.ty]`, run via the `ty` pre-commit hook
- **Linter / formatter**: **ruff** (100-char line length)

The workspace root is the repository root — written **`$PROJECT_ROOT`** in shell commands and
**`<root>`** in prose/paths. The venv is **always** `<root>/.venv`. See
*Tool Invocation — Absolute Paths Only* below for the one-time per-machine `$PROJECT_ROOT` setup.

## Project Structure

```
tcex_cli/
├── cli/                     # Typer command groups (one package per command)
│   ├── cli.py               # root Typer app; registers all commands
│   ├── cli_abc.py           # shared CLI base class
│   ├── app_input/  deploy/  deps/  migrate/  package/  run/
│   ├── spec_tool/  template/  validate/  model/
├── app/config/              # submodule
├── pleb/                    # submodule
├── requests_tc/             # submodule
├── util/                    # submodule
├── input/, logger/, render/, message_broker/   # parent-repo framework code
app/                         # sample/target App workspace used by run/deploy
tests/                       # pytest suite (mirrors commands: tests/<area>/)
```

User-facing commands (registered in `cli/cli.py`): `app-inputs`, `deploy`, `deps`, `init`, `list`,
`migrate`, `package`, `run`, `spec-tool`, `update`, `validate` (plus a conditional `test` command).
`init` / `list` / `update` are the template commands (`cli/template/`).

## Repository & Branching

This local repo is a **fork**. `origin` points at the fork; `upstream` is the ThreatConnect repo.

- **All work happens directly on the `main` branch** — `main` is the working branch here, not a
  protected trunk. Do **not** create feature branches; commit changes to `main` unless the operator
  has **manually** switched to another branch first.
- Claude Code must **never change branches itself** (enforced by `enforce_no_branch_change.sh`). If a
  branch change is genuinely needed, the human operator performs it; subsequent work then targets
  whatever branch is currently checked out.
- The usual "branch before committing on the default branch" convention does **not** apply to this
  fork — commits to `main` are expected (when the operator makes them — see below).

### Staging & commits are the operator's job — Claude never stages or commits

**Claude Code must NEVER create a git commit, and must NEVER stage changes (`git add`).** ALL staging
and commits — in the parent repo **and** in every submodule — are done by the **human operator**, who
reviews the working tree first. `git commit` is enforced by `enforce_no_commit.sh` (a PreToolUse hook)
and a `Bash(git commit:*)` deny rule; both block `git commit` in any form (`-m`, `-a`, `--amend`,
`git -C <submodule> commit`, after `&&`/pipes, …) with no override.

Claude's role stops at **preparing** the change and leaving it **unstaged** for human review:

- Make the edits and leave them in the working tree — do **not** `git add`.
- Run `git status` / `git diff` (unstaged) to show exactly what changed.
- **Report** what changed and the suggested commit message(s); the operator reviews, runs `git add`,
  then `git commit`.
- The same applies to submodule changes: describe the two-step commit + pointer bump, but let the
  operator stage and perform both commits.

## Git Submodules

Four parts of `tcex_cli/` are **independent git submodules**, each with its own repository and its own
`pyproject.toml`:

| Submodule path | Notes |
|---|---|
| `tcex_cli/app/config` | install.json / app-spec models + transform builder |
| `tcex_cli/pleb` | shared primitives (cached_property, registry, etc.) |
| `tcex_cli/requests_tc` | ThreatConnect session + auth |
| `tcex_cli/util` | general utilities (render, requests-to-curl, etc.) |

**Editing a submodule is a two-step commit:** commit the change **inside the submodule repo first**,
then bump the submodule pointer in the parent repo. Never assume a parent-repo commit captures
submodule edits. A single logical change can therefore span the parent repo and one or more
submodules.

> Each submodule also has its own `.pre-commit-config.yaml` and `[tool.ty]` config (kept in sync with
> the parent) so it type-checks standalone. There is no shared lockfile inside submodules — the `ty`
> binary is supplied by the parent venv.

## No Generated Code

Unlike the TcEx 4.0 framework, this project has **no V3 API code generator and no generated code**.
Every file under `tcex_cli/` is hand-maintained — edit it directly. (The `spec-tool` command *emits*
App spec/config files for downstream Apps, but that is product output, not source generated into this
repo.)

## Development Commands

Dependencies are managed with **uv**. The workspace root holds `uv.lock` and `.venv`; the root
`pyproject.toml` declares dependency groups, and each submodule has its own `pyproject.toml`.

```bash
# Sync the venv to the lock file (runtime + dev + test)
uv sync --group dev --group test

# Code quality (always use the venv's absolute binary paths — see Tool Invocation)
$PROJECT_ROOT/.venv/bin/ruff check .
$PROJECT_ROOT/.venv/bin/ruff format .
$PROJECT_ROOT/.venv/bin/ty check
$PROJECT_ROOT/.venv/bin/pre-commit run --all-files
```

**Managing dependencies:**

```bash
# Add a dev-only tool (root [dependency-groups].dev)
uv add --dev <package>

# Add a test-only tool
uv add --group test <package>

# Regenerate the lock file / sync
uv lock
uv sync --group dev --group test
```

- **Dev tooling** (ruff, ty, bandit, pyupgrade, pre-commit) lives in the **root** `pyproject.toml`
  under `[dependency-groups].dev`; **test tooling** (pytest, pytest-cov, pytest-ordering) under
  `[dependency-groups].test`.
- **Runtime deps** (typer, rich, fakeredis, …) live in `[project.dependencies]`.
- `uv` may be invoked by bare name (it lives on `PATH` and uses multi-word subcommands).

## Tool Invocation — Absolute Paths Only

**Rule:** every tool invocation MUST use an absolute binary path that is **statically rooted** — never
resolved dynamically. In **shell commands**, prefix the repo root with **`$PROJECT_ROOT`** (e.g.
`$PROJECT_ROOT/.venv/bin/ty check`); the venv is always `$PROJECT_ROOT/.venv`. `$PROJECT_ROOT` is a
fixed value injected from `.claude/settings.local.json` `env` — it is **not** dynamic resolution, so
it is allowed, unlike the forbidden `$(git rev-parse …)`, `$(pwd)`, `$(realpath …)`, `$(readlink …)`,
`$HOME`, or `source .venv/bin/activate`, which remain banned.

> **One-time per-machine setup.** `$PROJECT_ROOT` is **not** auto-populated, and `$CLAUDE_PROJECT_DIR`
> is **empty** in the Bash tool (it exists only for hook scripts). In the **untracked**
> `.claude/settings.local.json`, add an `env` block with the absolute repo path:
>
> ```json
> {"env": {"PROJECT_ROOT": "/abs/path/to/tcex-cli-2.0"}}
> ```
>
> then **restart Claude Code** so the value is injected into the Bash environment. `settings.local.json`
> is gitignored, so the absolute path is never committed; shared config (hooks, permissions, default
> agent) lives in the committed `.claude/settings.json`.
>
> **Read/Write/Edit tools do NOT expand env vars.** For plan paths and "read this file" references,
> use the `<root>` placeholder or a repo-root-relative path — never `$PROJECT_ROOT` in those contexts.

Three `PreToolUse` hooks (in `.claude/hooks/`) enforce this — treat them as hard rules:

- `enforce_no_dynamic_paths.sh` (Bash) — blocks commands containing path-resolving substitutions:
  `$(git …)`, `$(pwd)`, `$(realpath …)`, `$(readlink …)`, `$(cd … )` (and the backtick forms).
- `enforce_pinned_paths.sh` (Bash) — blocks **bare-name** invocations of standard system utilities;
  use the absolute path instead. It checks **every** command segment (split on `| || && ; |&`), so a
  bare name *after* a pipe is blocked too.
- `enforce_us_spelling.sh` (Write/Edit/NotebookEdit) — blocks British (en-GB) spellings in written
  content.

(Two further hooks — `enforce_no_commit.sh` and `enforce_no_branch_change.sh` — enforce the git rules
above.)

### Python / venv tools (always absolute `.venv/bin/…`)

```bash
# CORRECT
$PROJECT_ROOT/.venv/bin/python -c "..."
$PROJECT_ROOT/.venv/bin/pytest tests/template
$PROJECT_ROOT/.venv/bin/ruff check tcex_cli/cli/template/update.py
$PROJECT_ROOT/.venv/bin/ty check

# WRONG — re-prompts for every variant / blocked by hooks
cd <root> && .venv/bin/pytest
source .venv/bin/activate && python ...
python3 -c "..."
.venv/bin/pytest          # relative
```

Pass **absolute file paths as arguments**; do not `cd` first.

### System utilities — pinned to Homebrew GNU paths

This project standardizes on the **Homebrew GNU** builds of the standard utilities (coreutils, grep,
gnu-sed, findutils, gawk, gnu-tar, diffutils) in preference to the native macOS BSD tools.
`enforce_pinned_paths.sh` rejects bare-name invocations of these utilities and tells you the exact
absolute path to use. The pinned utilities and their paths:

| Tool(s) | Pinned path prefix |
|---|---|
| `cat head tail sort uniq wc cut tr ls cp mv rm mkdir chmod touch ln stat env date basename dirname tee echo printf du` | `/opt/homebrew/opt/coreutils/libexec/gnubin/` |
| `grep` | `/opt/homebrew/opt/grep/libexec/gnubin/` |
| `find xargs` | `/opt/homebrew/opt/findutils/libexec/gnubin/` |
| `sed` | `/opt/homebrew/opt/gnu-sed/libexec/gnubin/` |
| `awk` | `/opt/homebrew/opt/gawk/libexec/gnubin/` |
| `tar` | `/opt/homebrew/opt/gnu-tar/libexec/gnubin/` |
| `diff` | `/opt/homebrew/opt/diffutils/bin/` |
| `gzip gunzip zcat jq wget` | `/opt/homebrew/bin/` |
| `file` | `/usr/bin/` (no GNU build installed — stays native) |

The hook's `PINNED` map and the `settings.local.json` allowlist are the source of truth — keep all
three in sync. Examples:

```bash
# CORRECT — Homebrew GNU absolute paths
/opt/homebrew/opt/grep/libexec/gnubin/grep -r "pattern" tcex_cli/cli
/opt/homebrew/opt/findutils/libexec/gnubin/find tcex_cli -name "*.py" -type f \
  | /opt/homebrew/opt/findutils/libexec/gnubin/xargs /opt/homebrew/opt/grep/libexec/gnubin/grep "foo"

# WRONG — bare names; the hook blocks with a corrective message naming the exact path
grep -r "pattern" .
find . -name "*.py"
```

> Note: `git`, `docker`, and `uv` are not pinned (multi-word subcommands have their own rules);
> `curl` and `file` stay native (`/usr/bin/`).

## Code Standards

### Style and Language Conventions
- **Spelling**: strictly American English (US) for all natural-language output, code comments, and
  docs. The `enforce_us_spelling.sh` hook blocks en-GB variants.
- Prefer `-ize` over `-ise`, `-or` over `-our`, `-er` over `-re`, single `l` over `ll`
  (e.g. "initialize", "color", "center", "canceled").

### Python
- **Formatter / linter**: ruff, 100-char line length, config in root `[tool.ruff]`.
- **Type hints**: required; checked with **ty** (config in root `[tool.ty]`). The `tests/` tree is
  excluded. `python-platform = "linux"`, `python-version = "3.11"`.
- **Type-checker suppressions**: ty uses `# type: ignore` (blanket, PEP 484) and
  `# ty: ignore[<rule>]` (targeted). Legacy `# type: ignore[reportXxx]` codes do **not**
  work in ty. Prefer a real type fix; use a targeted `# ty: ignore[<rule>]` only when the code is
  correct but ty cannot infer it.
- **typer caveat**: typer does not yet support PEP 604 unions in some positions — `UP045`
  (`Use X | None`) is intentionally ignored for that reason (see `[tool.ruff.lint]`).
- **Docstrings**: Google style. **Imports**: organized by isort (`[tool.isort]`, 100-char).
- **pydantic v1** patterns throughout.

### Scripts CLI Standard — typer + rich, dry-run by default
Every operator-facing standalone script uses **typer** (CLI) + **rich** (output); mutating scripts
are **dry-run by default — pass `--commit` to write** (no `--dry-run`, no `--yes`). `temp_*` helpers
are exempt from the full standard. **All standalone scripts are authored by the
`python-script-specialist` agent** (see Agents).

### Bandit `# nosec` placement
The suppressor must sit on the **exact line** bandit flags, not a parent call. Always include the
specific test id and a justification, e.g. `subprocess.run(cmd)  # nosec B603 — args are static`.

### Shell / Bash
- **Never use `find -exec`** — pipe through `xargs` instead (`-exec` spawns a subprocess per match):
  ```bash
  /opt/homebrew/opt/findutils/libexec/gnubin/find tcex_cli -name "*.pyc" \
    | /opt/homebrew/opt/findutils/libexec/gnubin/xargs /opt/homebrew/opt/coreutils/libexec/gnubin/rm -f
  ```
  For paths with spaces, use `-print0` / `-0`.

## Testing

- pytest config in root `[tool.pytest.ini_options]`; `testpaths = ["tests"]`. Test ordering uses
  **pytest-ordering**; coverage via **pytest-cov**. If `.venv/bin/pytest` is missing, sync the test
  group once: `uv sync --group test`.
- Test layout mirrors the command surface: `tests/<area>/` — e.g. `tests/app`, `tests/deps`,
  `tests/init`, `tests/list`, `tests/run`, `tests/template` (plus `tests/conftest.py`).
- Redis-backed code (the `run` command's message broker / kvstore) is exercised with **fakeredis**.

```bash
$PROJECT_ROOT/.venv/bin/pytest                  # all
$PROJECT_ROOT/.venv/bin/pytest tests/template   # one area
$PROJECT_ROOT/.venv/bin/pytest -k "test_name"   # by pattern
```

## Agents

This project uses an orchestrator + specialist subagents (in `.claude/agents/`). The default agent is
`tcex-orchestrator` (set in `.claude/settings.local.json`).

| Agent | Use for |
|---|---|
| `tcex-orchestrator` | Analyzes the request, gathers context, writes a plan when required, delegates to specialists, then runs the security gate and reports. Does not write code itself. |
| `tcex-plan-reviewer` | **Plan-time adversarial review gate** (opt-in per task). Invoked by the orchestrator on a freshly drafted plan when the user opts in; returns severity-graded findings (🔴/🟠/🟡) and the orchestrator iterates to convergence before presenting it. Distinct from `python-security-auditor` (implementation-time). |
| `python-engineer` | **All** updates to the `tcex_cli` codebase under `tcex_cli/` (parent repo **and** submodules): CLI commands, models, framework logic, bug fixes, refactors, type-checker fixes, dependency changes. Not scripts, not tests. |
| `python-test-engineer` | **All** pytest test cases under `tests/`. Does not modify source. |
| `python-script-specialist` | **Sole author** of standalone scripts (typer + rich, dry-run/`--commit`). Writes to `.claude/scripts/`. |
| `python-security-auditor` | **Hard security gate** — runs after every code/test/script change; HIGH/critical findings block "done" until fixed. |

## One-Off Scripts (`.claude/scripts/`)

All standalone scripts are authored by `python-script-specialist`. Agent-written helpers live in
`.claude/scripts/` (the enforcement hooks live separately in `.claude/hooks/`). A genuine one- or
two-line `-c` invocation for
ad-hoc context-gathering is fine and does not need delegation. Python scripts must use the venv's
absolute `python` path.

| Script type | Prefix | Example |
|---|---|---|
| Reusable | _(none)_ | `audit_field_types.py` |
| Throwaway | `temp_` | `temp_check_counts.py` |

`temp_*` files are gitignored; reusable scripts are committed with the session.
