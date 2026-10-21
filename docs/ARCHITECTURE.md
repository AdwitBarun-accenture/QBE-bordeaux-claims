# Architecture

## 1. The pipeline at a glance

```
 email (M365 Graph) ─┐
 SFTP watcher ───────┼─► Intake ─► queue ─► [01 Ingestion] ─► [02 Mapping] ─► GATE 1 mapping sign-off
 UI upload ──────────┘   (raw stored                                             │ approve: semantic memory learns
                          write-once,                                            ▼
                          sha256, dedup)       [03 Validation] ─► [04 Cleansing] ─► [05 Classification] ─► [06 Reporting.prepare]
                                                                                                                 │
                                                                                          GATE 2 exception review
                                                                                                                 │ approve
                                                                                          [06 Reporting.prepare] (exclusions applied)
                                                                                                                 │
                                                                                          GATE 3 warehouse load sign-off
                                                                                                                 │ approve
                                                                                          [06 Reporting.load] ─► processed, episodic memory saved
                       Any gate → Reject ─► status 'rejected' + DUA email draft + episodic record
```

A gate is skipped automatically (an `auto` decision is recorded) only when it is switched
off in Settings **and** nothing needs a person. Agent work never runs inside an HTTP request:
the API enqueues a job (`workers/queue.py`: in-process thread pool locally, Azure Service Bus
in the cloud) and the UI polls.

## 2. Code map

| Package | Responsibility |
|---|---|
| `agents/` | One module per agent + `orchestrator.py` (state machine) + `base.py` (shared context, logging) |
| `rules/` | Rule framework (`base.py`), `common_rules.py`, `premium_rules.py`, `claims_rules.py`, `engine.py` (run + score) |
| `enrichment/` | 15 cleansing/enrichment steps with lineage; `pipeline.py` defines the order |
| `mapping/` | Deterministic matcher, formula evaluator, apply-mappings |
| `parsers/` | CSV (encoding/delimiter sniffing), Excel (sheet choice, title-row skip), decryption, file-type detection |
| `memory/` | Episodic, semantic and operational memory |
| `llm/` | Provider abstraction (Claude API, Claude in Foundry, Azure OpenAI, none) + prompts per agent |
| `loaders/` | Warehouse loaders (any SQLAlchemy DB incl. Postgres/Azure SQL/Snowflake; CSV for dev) |
| `storage/` | Local or Azure Blob; raw area is write-once |
| `connectors/` | Microsoft Graph mailbox, SFTP, webhook, poller |
| `security/` | JWT auth + roles, password vault (Key Vault or encrypted local) |
| `services/intake.py` | File arrival: store, fingerprint, identify coverholder, SLA, dedup |
| `api/` | REST endpoints used by the UI |
| `core/` | Settings, runtime (UI-editable) settings, LCRS schema |
| `reference_data/` | Code lists, FX, CRESTA, broker aliases – **placeholders, see its README** |

## 3. The agents

Every agent works without the AI. The model is used for judgement (ambiguous headers,
anomalies, free text, prose); arithmetic, rules, FX and loading are deterministic code.
Every action – including every model call with tokens and latency – is written to
operational memory and shown in the Agent activity feed with a correlation id.

### 01 Ingestion Agent — `agents/ingestion_agent.py`
1. Reads the immutable original from storage (stored at intake; SHA-256 recorded; an
   identical file is rejected as a duplicate before any processing).
2. Password handling: supplied password → vault → otherwise status `awaiting-password`
   (UI shows the unlock box; "save to vault" stores it in Key Vault).
3. Parses: CSV encoding + delimiter detection; Excel sheet selection and title rows above
   the header skipped; zip archives; duplicate headers made unique; empty rows dropped.
4. Classifies premium vs claims from headers + filename.
5. Recalls memory: prior runs (episodic) and approved mappings (semantic).
6. Detects layout changes vs the coverholder's last file (added/removed/reordered columns).

### 02 Mapping Agent — `agents/mapping_agent.py`
Cheapest method first:
1. **Semantic memory** – approved pairs for this coverholder + file type, 100%, no AI call.
2. **Deterministic matcher** – exact synonyms (95), the field's own name (90), value patterns
   such as UMR or claim-reference formats (90), fuzzy header similarity (86/65/50).
3. **AI** – only columns still below 95 go to the model. Agreement with the rule guess
   boosts confidence; disagreement is capped below the auto-approve threshold (→ review).
4. **Conflict resolution** – one source column per LCRS field.
5. **Status** – `auto` (≥ auto threshold, default 85), `review` (≥ review threshold, default
   50), `unmapped`. Free-text note columns stay unmapped and go to the Classification Agent.

Gate 1 opens if any column needs review, a mandatory field has no source, the layout
changed, or the gate is set to always-on. At the gate the analyst can re-target a column,
mark it unmapped or define a formula (`A×B`, `A÷B`, `A+B`, `A−B`, `A as % of B`, `B% of A`).
On approval, auto-mapped (≥ threshold), human-corrected and formula pairs are stored in
semantic memory.

### 03 Validation Agent — `agents/validation_agent.py`
Applies the approved mappings to build canonical rows, then runs the rule engine (section 4),
computes scores (section 5), optionally asks the model for anomalies the rules cannot see
(tagged `AI finding`, quoted rows only), stores severity-tiered exceptions with row numbers,
and writes resolution guidance (model, or a template if no model).

### 04 Cleansing Agent — `agents/cleansing_agent.py`
Runs the steps in `enrichment/pipeline.py` on a copy of the canonical rows. Every changed
value is recorded as `row, field, old, new, step` (the Value lineage panel).

| # | Step | What it does |
|---|---|---|
| 1 | Whitespace | Trim/collapse, strip control characters |
| 2 | Numbers | `1,250,000`, `2.5m`, `(1,200)`, `£45,200`, `12.5%` → plain numbers |
| 3 | Dates | DMY / MDY / text / Excel serial → ISO 8601 using the coverholder's date order; unparseable → row flag |
| 4 | Currency | Aliases (`Sterling`) → ISO 4217 |
| 5 | Country | Names → ISO 3166 alpha-2 |
| 6 | COB | `Property` → `PROP`, `Liability` → `LIAB` |
| 7 | Broker | Name variants → canonical name; fills a missing pseudonym |
| 8 | Claim status | `Settled` → `Closed`, `Part Paid` → `Open` |
| 9 | Handler | Email address → `H. Okonkwo` |
| 10 | Coverholder stamp | Fills `coverholder.name` |
| 11 | FX | Premium → `exchange_rate` + `gbp_equivalent`; claims → GBP incurred (pluggable `RateProvider`) |
| 12 | TMC code | COB → risk code taxonomy |
| 13 | Subscription share | Share %, calculated net (`derived.net_written_calculated`); fills net written **only if blank** |
| 14 | CRESTA | UK postcode → zone (sample table; production needs licensed data + geocoder) |
| 15 | Expense allocation | Brokerage and expense amounts per record |

### 05 Classification Agent — `agents/classification_agent.py`
Sources: unmapped note columns plus `risk.description` / `claim.description`. Regex extractors
handle common shorthand (endorsement dates, `prem adj -1200`, `DA limit 2.5m`, sub-limits,
deductibles, `+45k reserve mvmt`, cross-referenced `CLM-`/`POL-` refs, BI, subrogation,
general average, war, terrorism, TRIA, AMENDED). The model then extracts anything else; its
quoted source phrase must actually exist in the note. Each fact has a kind:

* `fact` – may fill a **blank** field if confidence ≥ the free-text threshold (default 70)
* `adjustment`, `cross_reference`, `flag` – stored as row annotations, never overwrite values

### 06 Reporting Agent — `agents/reporting_agent.py`
* **prepare** – builds the final dataset: per-row DQ flags from open/accepted exceptions;
  rows the analyst excluded are separated; claims rows found in a premium file are re-routed.
  Reconciliation is computed: received = to load + excluded + re-routed; raw-file SHA-256
  re-checked against storage; control total of the amount column source vs output; mandatory
  coverage; open duplicates; schema version. Then the executive summary.
* **load** – after Gate 3: one transaction into the warehouse table `dwh_lcrs_records`, then a
  read-back count to verify. Flagged rows load with `dq_status='flagged'` (100% preservation).
* **dua_email** – on rejection, drafts the coverholder email for the analyst to review.

### Insights Agent — `agents/insights_agent.py`
Dashboard computed from the warehouse, coverholder profiles, episodic memory and exception
history: GWP by class, files by month, DA utilisation (watch ≥ 75%, alert ≥ 90%), claims by
coverholder, quality trend, recurring exception patterns, AI token usage. Q&A answers are
grounded only on that computed context.

## 4. Business rules

Severity → exception tier: error → high, warning → medium, info → low.
A rule whose required fields are not mapped is reported as **Skipped**, never as passed.

| Rule id | Applies to | Severity | Dimension | Check |
|---|---|---|---|---|
| MANDATORY | both | error | completeness | Mandatory LCRS fields populated (see section 6) |
| CCY_ISO | both | warning | accuracy | Currency is ISO 4217 |
| DATE_FORMAT | both | warning | consistency | Year-only, invalid, other-order dates; ambiguous dates when the file mixes orders or no profile exists |
| COUNTRY | both | info | accuracy | Country recognised |
| INC_EXP | premium | error | consistency | Inception before expiry |
| DUP_UMR | premium | error | consistency | Same UMR + policy ref twice in the file |
| DUP_PRIOR | premium | warning | consistency | UMR already loaded in a prior submission |
| NET_ARITH | premium | error | accuracy | Net written ≈ gross × signed line % (1% / 1 unit tolerance) |
| EML_PROP | premium | warning | completeness | EML present for PROP/ENGY |
| SI_PRESENT | premium | error | completeness | Sum insured declared and > 0 |
| COB_CODE | premium | warning | accuracy | COB in the taxonomy |
| MIXED_TYPES | premium | error | consistency | Claims rows inside a premium file |
| BRKG_CAP | premium | info | accuracy | Brokerage ≤ cap (default 15%) |
| PCT_RANGE | premium | error | accuracy | Line / EML / brokerage / expense between 0 and 100 |
| PREM_NUM | premium | error | accuracy | Gross premium numeric |
| BKR_CODE | premium | warning | completeness | Broker pseudonym present |
| BKR_NAME | premium | info | consistency | One broker written several ways |
| DA_LIMIT | premium | warning | accuracy | YTD written (warehouse + this file, GBP) vs coverholder DA limit |
| LOSS_NOTIF | claims | error | consistency | Loss date ≤ notification date |
| LOSS_FUTURE | claims | error | accuracy | Loss date not in the future |
| RESERVE_ARITH | claims | error | accuracy | Paid + outstanding = total incurred |
| DUP_CLAIM | claims | error | consistency | Claim reference repeated (notes differing reserves) |
| DOL_PRESENT | claims | warning | completeness | Date of loss present |
| CLAIM_STATUS | claims | info | accuracy | Status in taxonomy |
| HANDLER_FMT | claims | info | accuracy | Handler is a name, not an email |
| NEG_RESERVE | claims | warning | accuracy | No negative reserves/paid |

Add a rule: create a class in the right module with `@register`, set `id`, `severity`,
`dimension`, `applies_to`, `requires`, implement `check()` returning failing row numbers.

## 5. Quality scores

* **Completeness** = populated mandatory cells ÷ (rows × mandatory fields).
* **Accuracy / Consistency** = 100 − penalty, where a row failing an error-level rule on that
  dimension costs 1 row and a row failing only warning-level rules costs ½; info rules cost 0.
* **Overall** = weighted average (weights in Settings → `quality_weights`).

## 6. Data schemas

### LCRS canonical model (`core/lcrs_schema.py`)
48 fields in 7 groups, each with type, mandatory flag and header synonyms.

| Group | Fields |
|---|---|
| policy | unique_market_reference*P, reference*C, inception_date*P, expiry_date*P, endorsement_date, cancellation_date, status |
| insured | name*P*C, reference, address, country |
| risk | class_of_business*P, tmc_code†, description, address, country, sum_insured, eml_percent, cresta_zone†, postcode |
| premium | gross_original*P, net_written, currency*P, exchange_rate†, gbp_equivalent†, signed_line, subscription_share†, expense_ratio, brokerage |
| claim | reference*C, date_of_loss*C, date_reported*C, description, loss_type, reserve_gross, paid_to_date*C, outstanding*C, total_incurred*C, currency*C, status*C, handler, coverage_type |
| broker | name, reference, pseudonym |
| coverholder | name, reference, binding_authority |

`*P` mandatory for premium, `*C` mandatory for claims, `†` produced by enrichment.
Extension fields (not LCRS): `derived.net_written_calculated`, `derived.brokerage_amount`,
`derived.expense_amount`, `derived.claim_gbp_incurred`.

> The mockup calls this "LCRS v3.2". The real Lloyd's Coverholder Reporting Standards use
> different field names; align this one file with the version your market uses.

### Mockup source layouts (`sample_data/`)
* Premium (19 cols): Insured, UMR, Our Ref, On Risk Date, Off Risk Date, Gross Prem, Net Prem
  Written, Ccy, Sum Ins, Class, EML, Location, Cntry, Broker, Bkr Code, Our Line %, Exp Ratio, Comm %, Notes
* Claims (14 cols): Insured Name, Policy No, Claim Ref, Loss Date, Notified, Cause of Loss,
  Gross Reserve, Ccy, Paid, O/S Reserve, Total Incurred, Status, Handler, Type of Loss

### Pipeline artefacts
Datasets in staged storage per run: `parsed`, `canonical`, `enriched`, `final`, `rerouted`,
`lineage`. JSON stage outputs on `pipeline_runs`: `ingestion`, `mappings`
(`source, canonical, confidence, origin, status, notes, samples, formula`),
`structural_change`, `validation` (`checks, scores, date_order, ai_findings`), `enrichment`,
`freetext`, `reconciliation`, `summary`, `resolution_guidance`, `load_result`.

### Database tables (`db/models.py`)
`users`, `coverholders`, `bdx_files` (inbox), `pipeline_runs`, `data_exceptions`,
`hitl_decisions`, `semantic_mappings`, `episodic_memory`, `operational_log`, `app_settings`,
`connector_state`; warehouse: `dwh_lcrs_records`.

## 7. Differences from the mockup (and why)

| Mockup | This build |
|---|---|
| 4 of 6 inbox files were pre-baked results | Every file runs the real pipeline |
| LLM invented the rule checks and scores | 26 coded rules, computed scores; AI adds anomalies only |
| Mapping fallback = column *i* → field *i* | Deterministic matcher; AI only for ambiguous columns |
| Enrichment overwrote stated net written | Stated value kept; calculated net stored separately; mismatch is an exception |
| Free text overwrote real fields (`prem adj` → gross, `Ded 100k` → premium, `30d notice` → date) | Only facts fill blank fields; adjustments/flags are annotations |
| Free-text rows matched by insured's first word | Matched by source row number |
| DD/MM assumed; `04/15/2026` broke | Order per coverholder; MDY detected; mixed files flagged |
| `Sterling` fell to rate 1.0 | Alias → GBP |
| CRESTA, expense allocation were labels | Implemented (CRESTA with sample data) |
| Reconciliation hard-coded to pass | Computed; SHA-256 re-check; control totals |
| Snowflake commit was a feed message | Transactional load + read-back verification |
| Reject = `alert()` | DUA email draft, rejected status, episodic record |
| Passwords in browser `localStorage` | Key Vault / encrypted vault |
| Memory lost on refresh | Database tables |
| Insights from hard-coded numbers | Computed from the warehouse |
| API key would be exposed in the browser | All AI calls server-side |

## 8. Extending

* **New warehouse:** set `DWH_DATABASE_URL` to any SQLAlchemy URL, or implement `loaders/base.Warehouse`.
* **New AI provider:** implement `llm/base.LLMProvider` and register it in `llm/client.py`.
* **New enrichment step:** subclass `enrichment/base.Step`, add to `default_steps()`.
* **New connector:** return `IncomingFile` objects and add it to `connectors/poller.py`.
* **Real FX:** implement `enrichment/fx.RateProvider.get_rate(ccy, date)`.
