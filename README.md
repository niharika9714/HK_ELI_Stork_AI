# HK ELI · Stork AI Flask application

Separate application; existing Dify workflows are unchanged. Python 3.11+.

## Run the synthetic mock UI

From the HKELI workspace in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r HK_ELI_Stork_AI/requirements.txt
Copy-Item HK_ELI_Stork_AI/config.example.toml HK_ELI_Stork_AI/config.local.toml
Set-Location HK_ELI_Stork_AI
..\.venv\Scripts\python.exe run.py
```

Open `http://127.0.0.1:8020`. Select Hong Kong Sales or Singapore Sales. HK has the synthetic HK dashboard entitlement; SG has no dashboard entitlement. The server checks permissions independently of UI controls. Demo uses a small deterministic planner for the listed examples, not Stork AI. All demo data is synthetic; demo references are explicitly not real Tableau citations.

Try these individually:

1. Show client holdings.
2. Filter active holdings.
3. Aggregate sub-product to product.
4. Show notional by maturity year.
5. Show a pie chart by product.
6. Compare product and sector.
7. Show total notional.
8. Show client holdings and summarize it.
9. Show profit. (Specific missing-metric explanation.)
10. Switch to Singapore and attempt the HK dashboard. (Denied before retrieval.)

Demo matching is deliberately limited and is not semantic acceptance of arbitrary paraphrases. Live Stork planning uses the actual catalog and then the actual received schema. No cross-export joins are permitted. Case (e) requires a single approved export containing both dimensions; a relationship existing elsewhere in Tableau does not establish that the exported worksheet contains them.

## Configuration: one segmented file

`config.local.toml` contains `[app]`, `[stork]`, `[tableau]`, `[identity]`, `[[dashboards]]` and `[[users]]`. It is ignored by Git. Secrets are environment-variable references, not committed values. Add independent dashboard registry entries for additional countries/business units and exact published names. An authorized workbook does not automatically authorize all worksheets: configure verified dashboard membership in `worksheet_names`.

### Stork AI

User-supplied private SDK contract is implemented in `app/integrations/vertex_adapter.py`:

```python
from ada_genai.google_genai import VertexClient
client = VertexClient()
response = await client.aio.models.generate_content(
    model="gemini-3.5-flash", content=prompt)
```

Provision `One_Bank_ID`, `One_BANK_PASSWORD`, `SSL_CERT_FILE` in the service environment before startup. The adapter uses the supplied singular `content` argument and asynchronous call with a timeout. Install the bank-approved private `ada_genai` distribution through the office package channel; it is not substituted with a public similarly named package. Neither that SDK nor the model identifier was available for a real call here. Environment consumption by the private SDK needs office verification. Configuration references alternative environment variable names only for validation; ensure the SDK-required canonical names are provisioned.

### Live Tableau and identity

- Set `app.mode="live"`, persistent `HKELI_SESSION_SECRET`, HTTPS/secure cookies, trusted Tableau HTTPS origin, site (blank allowed), API version supported by your server, Connected App client/secret IDs and secret environment variable.
- Set a server-side identity resolver `module:function`. It receives the Flask request and returns a **verified** identity with `id`, `country`, `line_of_business` and `tableau_username`. It must validate SSO tokens/groups; do not trust unsigned browser headers or user-entered identity fields. Mock login is disabled in live mode. An actual corporate SSO adapter cannot be supplied without its issuer/audience/claims contract.
- The country/LOB registry restricts discovery before the LLM sees metadata. Only selected authorized dashboards enter the plan. Discovery uses paginated workbooks, exact unique names, then workbook views restricted by the author-approved dashboard membership list.
- Tableau REST and embedding both use the mapped user's identity. **Actual row-level entitlements must be enforced in Tableau's published content/data policy** as well as dashboard access. Do not use a shared administrator Tableau subject to bypass that policy.
- Configure exact additive metrics, date fields, snapshot axes and supported per-view filters. Live registry values are administrator assertions that need verification; the example synthetic definitions must be replaced for real data.
- Set the Connected App embedding-domain/project allowlist for the new frontend origin. The frontend dynamically loads Embedding API v3 from the server-discovered Tableau origin. Only an embed JWT reaches the browser, fetched separately from saved chat answers. REST sessions close in `finally`; failures never trigger PAT fallback.
- `TABLEAU_CA_BUNDLE` may be blank for default verified roots, an approved absolute CA path or inline PEM text. The existing verified transport was copied into the standalone app and adapted to allow absolute Windows paths. Stork's `SSL_CERT_FILE` is independent.

## Layout

```text
app/
  controllers/api.py           REST endpoints, CSRF and request validation
  integrations/stork.py        Typed prompt/response boundary
  integrations/vertex_adapter.py  User-supplied private SDK call contract
  integrations/tableau.py      Direct Trust JWT, sessions, discovery and CSV
  services/identity.py         Identity and dashboard authorization
  services/orchestrator.py     Native Python routing and failure isolation
  services/analysis.py         Validated DuckDB analysis; no LLM SQL execution
  services/jobs.py             Bounded asynchronous work and owner checks
  services/demo.py             Clearly synthetic fixture and example planner
  models.py                   Strict typed plans
  templates/, static/         Chat-only mock UI and responsive SVG charts
tests/                        Synthetic API/entitlement/large-data tests
```

API: `GET /api/session`, demo-only `POST /api/login`, `POST /api/logout`, `GET /api/dashboards`, `POST /api/chat` (202 + job ID), `GET /api/jobs/{id}`, `POST /api/embed-token`. POST requests require the session's `X-CSRF-Token`. Job endpoints check owner and current dashboard entitlement. The app exposes no arbitrary URLs, SQL, Python evaluation or user-supplied Tableau identity.

## Analysis, citations and performance

Original views use Tableau Embedding API v3, not reconstruction. Requested filters are applied only if explicitly declared supported. Custom bar/pie/line/heatmap renderers use validated compact results; they are labeled as calculations over the cited export. Exact values remain in the table; SVG floating-point limits refuse unsafe chart values. Unknown mean/deal-count semantics are refused. Unknown financial formulas or missing fields produce gaps, not automatic access-denial messages.

Live numerical responses link `[T1]` to the actual discovered Tableau source and retain scope. Clarification/login/access errors cannot honestly cite unseen Tableau values and do not fabricate citations. The implementation returns deterministic result tables and a cited scope statement; a free-prose LLM financial narrative is intentionally not enabled without a separate grounding validator. Original tooltips/actions are native Tableau; custom tooltips contain only returned values. Browser filter changes do not refresh earlier numerical answers.

Jobs return immediately for polling; maximum two concurrent jobs and 16 retained/queued jobs by default. Excess capacity returns 429. No unbounded agent loop: live analytical requests make at most two Stork planning calls. DuckDB performs full-input filtering/grouping with one database thread per job, 256MB memory budget, no disk spill, and a 30-second calculation interrupt. CSV streams to a private temporary file (64MB default), which is deleted after processing. Row capacity is 250,000; result capacity 200. Oversized results fail rather than silently truncating a chart. Temporary disk storage requires office approval for financial data. CSV is a published summary export, not proof of underlying-record completeness.

**Capacity limits, not a no-timeout guarantee:** CSV parsing is bounded by bytes/rows and DuckDB memory but is not currently interrupted by the calculation timer. Network requests have connection/read timeouts; no end-to-end hard process deadline or cancellation endpoint is implemented. Slow remote trickle responses or a noncooperative private SDK can require process-level isolation in production. Optional summary errors preserve the original view, though this initial polling API returns the completed answer together rather than streaming its native card early.

The job store is **single-process, in-memory, expiring on access**. Completed results expire after 15 minutes; capacity is reclaimed on the next submission. Restart loses jobs. Do not run multiple WSGI processes against this store. For a multi-instance production rollout, replace the job repository/executor with a shared owner-scoped job store and bounded worker processes, add hard deadlines/cancellation, per-user rate limits, measured load tests, audit redaction, CSP and corporate SSO. More concurrency is not safe merely by increasing threads. Per-user Tableau sessions are not shared or cached.

For a single-process staging deployment, from this folder:

```powershell
..\.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:8020 --threads=8 run:app
```

Use an approved HTTPS reverse proxy for hosting. Flask development server is local demo only. See [Flask deployment guidance](https://flask.palletsprojects.com/en/stable/deploying/).

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s HK_ELI_Stork_AI/tests -v
node --check HK_ELI_Stork_AI/app/static/app.js
```

Ten synthetic tests pass: HK/SG authorization, CSRF, disabled live mock login, job isolation, cases (a–f), unknown metric, unsupported native filters, unauthorized model source, optional-summary failure isolation, private SDK call contract and exact aggregation of 100,000 rows. Python compilation passes. Node is unavailable in this environment, so the JavaScript syntax command above and interactive browser acceptance remain to be run. Tested packages include Flask 3.1.3, DuckDB 1.5.6, Waitress 3.0.2 and Requests 2.34.2. No real credentials/private exports used. Live Stork/Tableau, bank identity mapping, browser embedding fidelity and multi-user load capacity remain unverified.

Official API design references: [Tableau REST workbooks/views](https://help.tableau.com/current/api/rest_api/en-us/REST/rest_api_ref_workbooks_and_views.htm), [Connected App authentication](https://help.tableau.com/current/online/en-us/connected_apps_direct.htm).
