# Testing gaps

`tests/test_geometry.py` covers `paralia_sdk.geometry` reasonably well (format round-trips, alignment, welding). Nothing else in the package has tests yet. This is a map of what's untested and why it matters, for whenever there's time to close the gap — not a todo list to rush.

## `http.py` (`BaseClient`) — highest priority

This is the riskiest untested code in the package: it's the one place a subtle bug would silently affect every client built on it.

- **Auth header injection** — does every request actually carry `X-Internal-Secret`? Does a custom header passed to `_request` correctly merge with (not replace) it?
- **Retry-on-transport-failure** — does a connection error get retried exactly `max_retries` times, then raise `ParaliaAPIError` wrapping the original exception? (Easy to test with a mocked `requests.Session` that raises on the first N calls.)
- **Non-2xx handling** — does a 4xx/5xx response raise `ParaliaAPIError` with the right `status_code` and `body` (both the JSON-body case and the non-JSON-body case)?
- **Response body parsing** — empty body → `None`; `application/json` content-type → parsed dict; anything else → raw bytes.
- **`max_retries < 0` validation** — should raise `ValueError` at construction time.

## `paradigm_client.py` (`ParadigmClient.run_pipeline`)

- Does it build the request correctly for the common cases: `case_id` provided vs. omitted, `sdf_backend` provided vs. omitted, `include_heatmap` true vs. false — confirm the right headers get sent/omitted in each case.
- Does `ParadigmRunResult` get built correctly from a realistic response payload (success case, failure case, heatmap-included case)?

## `parable_client.py` (`ParableClient`)

- Each method's URL construction (`/runs`, `/runs/{id}/status`, `/runs/{id}/data/{path}`, etc.) against a mocked backend.
- `run_data`'s dual return shape — bytes for `.csv`/`.stl`, a parsed dict for `.json` — is easy to get wrong if the underlying content-type logic in `http.py` ever changes; a test pinning this behavior would catch that early.

## How to approach it

None of this needs real network calls — `requests` has good mocking support (`responses` or `unittest.mock.patch` on `requests.Session.request` both work well here), so a test suite for this file wouldn't need a live paradigm/parable service running.
