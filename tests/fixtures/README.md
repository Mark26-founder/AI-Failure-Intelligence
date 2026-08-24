# AIFI Test Fixtures Guide

This directory contains realistic execution trace fixtures used for end-to-end integration and pipeline testing in Phase 9.

| Fixture File | Description / Failure Scenario | Expected Detection | Expected Diagnosis | Reproduction Support | Verification Outcome (vs `postfix_success.json`) |
|---|---|---|---|---|---|
| `tool_execution_failure.json` | Python calculator tool attempt divided by zero. | `tool_execution_failure` | Points to `call_calc_001` with `ZeroDivisionError`. | **Supported** (with registered runner) | `fixed` |
| `repeated_action_loop.json` | File searcher called `search_dir` 3 times with identical parameters. | `repeated_action_loop` | Highlights 3 consecutive identical calls to `search_dir`. | `unable_to_reproduce` (requires agent runtime) | N/A |
| `execution_error_event.json` | Cloud worker timed out connecting to HTTP API. | `execution_error_event` | Identifies `ConnectionTimeoutError` event. | `unable_to_reproduce` (requires agent runtime) | N/A |
| `invalid_tool_selection.json` | Agent requested non-existent/deprecated tool (`deprecated_db_query`). | `invalid_tool_selection` | Pinpoints invalid tool `deprecated_db_query`. | `unable_to_reproduce` (requires agent runtime) | N/A |
| `unresolved_tool_call.json` | Agent started async job `call_async_99` but trace terminated before result. | `unresolved_tool_call` | Flags unreturned call `call_async_99`. | `unable_to_reproduce` (requires agent runtime) | N/A |
| `clean_success.json` | Successful calculation workflow completing with a `final_result`. | None (`has_failures: false`) | N/A | N/A | N/A |
| `postfix_success.json` | Corrected execution where `call_calc_001` divides by 5 instead of 0. | None (`has_failures: false`) | N/A | N/A | `fixed` |

## Usage in End-to-End Tests

All fixtures are validated using `aifi.validate_trace` and processed through the top-level `aifi` public API in `tests/test_e2e_pipeline.py`.
