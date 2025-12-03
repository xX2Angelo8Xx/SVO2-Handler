# Coding Guidelines

These conventions aim for maintainable, testable, and readable code aligned with common industry practices.

## General
- Prefer Python 3.10+ with full type hints. Enable strict type-checking (`mypy --strict`).
- Follow PEP 8 formatting; run `ruff`/`black` (or chosen formatter) before committing.
- Keep functions small and single-purpose; extract helpers instead of adding flags that change behavior.
- Fail fast with clear error messages; return structured errors where useful for the UI.
- Avoid premature optimization; measure with profiling when performance matters (decoding/writing loops).

## Project structure
- `src/svo_handler/` hosts all app code. Keep UI, ingestion, pipelines, and IO concerns in separate modules.
- `config/` stores defaults and templates—do not hardcode paths or formats in code.
- `scripts/` for reproducible CLI tasks (packaging, dataset prep). Keep them idempotent.
- `tests/` mirrors `src/` structure; use fixtures/mocks for ZED dependencies where possible.

## Style and patterns
- Use dependency injection for I/O heavy components (ingestion, storage) to simplify testing.
- Prefer dataclasses for configuration/state objects; keep them immutable when feasible.
- Log with structured context (source file, options, frame counts). Avoid printing from libraries.
- Separate UI thread from worker tasks; communicate via signals/queues, not shared mutable state. Monitor/worker loops must break on stop/cancel paths (avoid `continue` that wedges shutdown) and be joined from the controller layer.
- Validate all user inputs (paths, FPS ranges, depth model availability) at boundaries.

## Exceptions and errors
- Raise domain-specific exceptions for ingest/extraction issues; let the app layer map them to UI messages.
- Catch broad exceptions only at the app boundary; log and surface actionable guidance to the user.

## Testing
- Write unit tests for:
  - FPS downsampling math (`skip every n` frames).
  - Option validation (target FPS vs. source FPS, stream selection).
  - Manifest generation and output path building.
- Treat per-frame decode failures as recoverable in tests (simulate `CORRUPTED_FRAME`-style events and ensure the pipeline continues with logging).
- Integration tests: use tiny `.svo2` samples or mocked ingestion to keep CI fast.
- Ensure deterministic tests; avoid depending on wall-clock time or local paths.

## Documentation
- Keep module/class docstrings describing intent, inputs, and outputs.
- Update `README.md` and `docs/architecture.md` when altering flow, dependencies, or outputs.
- For public functions, include concise docstrings with args/returns and error cases.

## Git hygiene
- One logical change per commit; keep messages imperative (e.g., “Add FPS downsampling helper”).
- Run linters/tests before pushing. Do not commit generated artifacts or sample binaries.
