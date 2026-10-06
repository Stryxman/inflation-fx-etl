# Contributing

## Workflow

1. Create a branch named `feat|fix|docs/<issue-number>-<slug>`, for example `feat/2-local-infrastructure`.
2. Write the test first, watch it fail for the right reason, then write the minimum code to pass.
3. Open a pull request that says `Closes #<n>`. CI must be green before merging.

## Naming

- **Python:** `snake_case` for modules, functions and variables; `PascalCase` for classes; `UPPER_CASE` for constants. Ruff rules `N` enforce this.
- **SQL:** `snake_case` everywhere; tables are always written `schema.table`; files are named `NN_name.sql` (two-digit prefix gives the execution order).
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/), for example `feat(config): load country scope`.

## Code quality

- Every module, class and public function has a Google-style docstring (ruff rules `D`, convention `google`; not required in `tests/`).
- `mypy etl` runs in strict mode and must pass.
- `ruff check .` and `ruff format --check .` must pass.

## Tests

- Unit tests never use the network; HTTP is mocked or replaced by fixtures.
- Tests that touch the database carry the `db` marker and use the `etl_test` database through the `db` fixture. Locally they are skipped when the database is unreachable; in CI (`CI=true`) an unreachable database is an error.
- Coverage must stay at or above 85 % (`make test` fails below that).

## Logs

- Use `etl.log.get_logger(__name__)`. Never call `print`, except for the final summary of the CLI.
- Levels: `INFO` for steps, `WARNING` for retries, `ERROR` for failures, `DEBUG` for detail.
- Log URLs without credentials. The CLI exposes `--log-level`.
- Any dataclass or object carrying connection credentials declares them with `field(repr=False)`; never log a DSN unredacted.

## Performance

- Each source records `fetch_ms`, `parse_ms` and `load_ms` in `audit.etl_runs` and in the run summary. No threshold is enforced; the first real load is the reference measurement (`docs/performance.md`).
