# Testing

Full write-up: `KnowledgePulse_Testing.docx`. This is the quick reference.

```bash
pip install -r backend/requirements-dev.txt     # pytest, once
cd frontend && npm ci && cd ..                  # for the frontend layer, once

./run-tests.sh                    # frontend, integration, acceptance, regression
./run-tests.sh acceptance         # one layer
./run-tests.sh live               # real models; needs API keys in backend/.env
./run-tests.sh e2e                # browser test; pip install playwright, playwright install chromium
```

Windows: `.\run-tests.ps1` with the same layer names
(`powershell -ExecutionPolicy Bypass -File .\run-tests.ps1` if scripts are blocked).

| Layer | What | Time |
|---|---|---|
| frontend | type check, build, export API types for the contract test | ~15 s |
| integration | components together: crawl, index, chat, analytics, workspaces, tenancy, scripts, frontend contract | ~1 min |
| acceptance | one test per FR/NFR in the report, plus seven user journeys; writes traceability.md | ~1 min |
| regression | fixed bugs, known-answer formulas, smoke test, tenancy suite | ~40 s |
| live | real embedding model and LLM | a few min |
| e2e | real Chromium through the frontend: sign-in, sign-out, workspace switching, conversation persistence (needs Playwright) | ~1 min |
| tenancy, smoke | the two standalone checks on their own | seconds |

No API keys, no model download and no network are needed except for `live`.
Nothing touches `backend/.env` or the real database, except `live`, which reads
the keys but still uses temporary storage.

Reports land in `backend/test-reports/`: `<layer>-junit.xml`,
`<layer>-results.json`, and `traceability.md` after the acceptance layer.

Conventions:
- Tag acceptance tests with `@pytest.mark.req("FR6")`; the matrix is built from the tags.
- A known gap or defect is `xfail(strict=True)` with a reason starting "Known gap:" or
  "Defect found in testing:". When it gets fixed the test passes, strict makes the run
  fail, and you remove the marker. The matrix can never go stale.
- Every test gets its own organisation id, so tests never see each other's data.
