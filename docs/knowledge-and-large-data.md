# Business knowledge and full-export analysis

The Flask framework, controller/service structure, job queue and existing Stork adapter are retained. Dify files are unchanged.

## Connect a business knowledge pack

Merge these settings into your existing `config.local.toml`; do not replace your configured credentials or identity settings:

```toml
[knowledge]
demo_pack = "knowledge/mock-ui"
max_characters = 80000
max_prompt_characters = 120000
```

Inside each existing `[[dashboards]]` entry, add:

```toml
knowledge_pack = "../knowledge/hkeli-demo"
```

Paths are relative to `HK_ELI_Stork_AI`, or administrator-configured absolute paths. Restart the app after configuration changes. Packs are read for each job; there is no separate knowledge service or Dify dependency. Copy the example pack to a business-owned folder to maintain independent definitions.

Use the existing `knowledge/hkeli-demo` pack as the format example:

- `catalog.json`: exact workbook content URL and view name, purpose, limitations, grain, native capabilities, column units/types/additivity, supported filters and export verification.
- `views/*.md`: business descriptions, questions answered, interpretation and limitations. Reference each file using the view record's `source_document`.
- `documents/*.md`: shared glossary, product definitions, calculation/calendar policies and lineage.

Business owners edit definitions and descriptions; a Tableau/data owner verifies export columns, grain, date roles, units, additivity and supported filters before marking `verified_export=true`. The real-dashboard example deliberately remains unverified. The separate `knowledge/mock-ui` contract is verified only for its synthetic fixture and must not be used for real Tableau data.

Only authorized, selected dashboards enter discovery. All discovered candidates remain visible to the existing source-selection LLM, with every matching structured record, relevant view document and complete shared documents from its configured pack. There is no Python semantic ranking or keyword whitelist. Pack shared documents must be appropriate for every authorized reader of that pack; use separate packs for different audiences. Knowledge is reference material, not permission to execute code or access another view.

The existing source call interprets measures, dimensions and conditions, compares all candidates and returns an assessment of the selected source. Python checks JSON/schema, authorized identity, original-question quotations and internal assessment consistency. It does not independently prove semantic correctness. For example, a scalar P&L KPI cannot satisfy notional distributed by product; this distinction is explicit in the model prompt. A confidently wrong model answer still requires investigation.

Complete context is bounded: oversized packs/prompts fail explicitly instead of dropping candidates or documents. This is full scoped context, not retrieval over an unlimited enterprise knowledge base. Narrow authorized dashboard scope as the catalog grows.

## Full CSV calculations

Analytical requests download one bounded authorized CSV into a private temporary directory. DuckDB loads and calculates over every received row. The second existing Stork call receives the actual schema, full row count and approved metric contracts, not the CSV. Python executes typed operations with parameterized values; model-generated SQL/code is not executed. Temporary exports are deleted when the job finishes.

The example supports 100,000 rows within configured row, cell, file and memory limits. Output has a separate display limit; exceeding it fails rather than truncating a chart. Calculation timers cover import and execution. Unknown/unverified additivity, incompatible schema, multiple snapshot dates rolled into a total and missing summed values produce explicit failures. Plain published-view requests skip CSV analysis. Optional analysis failure preserves the original view.

The bounded single-process queue remains in place. Capacity limits and timeouts protect resources; they do not guarantee every arbitrarily wide CSV or concurrent workload completes. Durable distributed jobs and production load sizing remain separate work.

## Diagnose and validate selection

Inspect the job API response's `source_selection`: original-question requirements, `request_understanding`, selected dashboard/view and `selection_assessment`. Definition references are separate from Tableau numerical citations. In live mode the source prompt includes the original question twice and treats examples/catalog prose as reference, preventing the earlier copying of a dashboard description as the user's request.

Test `Show how the notional is distributed across product types.` in live mode with the example pack and correctly discovered workbook: expect Product Mix if its recorded purpose is accurate. Test unrelated paraphrases, explicit filters, unsupported knockout requests and denied dashboards as well. Demo mode uses externally stored synthetic scenarios and does not establish live model quality.

Run local checks from the workspace root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s HK_ELI_Stork_AI/tests -v
```

Tests cover complete scoped knowledge reaching the adapter, copied intent, incomplete assessments, unauthorized sources, novel paraphrases, knowledge capacity, and a 100,000-row calculation with an outlier in its last row. Live Stork, corporate SSO and Tableau acceptance must be performed in the configured office environment.
