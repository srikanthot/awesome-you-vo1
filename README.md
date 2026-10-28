# AML Alert Triage POC

A proof of concept that triages anti-money-laundering transaction-monitoring alerts. It reads a
work item from the Alessa case manager (read-only), masks personal data, asks a language model to
recommend a disposition with a draft analyst comment, and presents the result for a human analyst
to approve.

**Scope:** Alessa transaction-monitoring alerts only.

## How it works

```
extract (read-only)  ->  mask PII  ->  triage (LLM)  ->  analyst review  ->  write-back*
```

- **Extract** – reads the Entity 360 work item (entity, alerts, triggering transactions, full
  transaction history, action/comment history) through Alessa's own data calls. It only ever
  sends a fixed allow-list of read calls; it cannot modify anything in Alessa.
- **Mask** – replaces names, accounts and other identifiers with consistent tokens *before* any
  model call. The token map stays internal and is used only to restore the final comment.
- **Triage** – a model applies the business rules to the masked case and returns a recommendation
  (close / escalate / needs review), reasons, the transactions cited, and a draft comment.
- **Review** – the recommendation and unmasked comment are written out for an analyst to approve.
- **Write-back** (not in this POC) – once approved, the comment is added back to Alessa.

## Project layout

```
alert_triage/
  settings.py        runtime settings (storage, model) from environment
  storage.py         case storage: local folder now, Blob later
  llm.py             model client: a stub for local work, APIM/Foundry when available
  config.py          extractor configuration (config/alessa.yaml)
  pipeline.py        mask -> triage -> review over extracted cases
  extractor/         read-only Alessa extraction (endpoints, client, session, case builder, CLI)
  masking/           PII masking and unmasking
  agent/             triage agent: prompt, output schema, case summary
config/              alessa.example.yaml, pii_fields.yaml, sop/
automation/          Power Automate Desktop version of the extraction
tests/               bundled mock server + tests (no live environment needed)
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate                              # Windows; source .venv/bin/activate elsewhere
pip install -r requirements.txt
cp .env.example .env                                # fill in as needed
cp config/alessa.example.yaml config/alessa.yaml    # fill in base_url and the result-set values
```

The extractor uses the installed Edge, so `playwright install` is not required on the workstation.
Install `requirements-azure.txt` as well once cloud access (Blob, APIM/Foundry) is available.

## Usage

```bash
# 1. Extract work items (a browser opens; sign in with your authenticator code)
python -m alert_triage.extractor.run --config config/alessa.yaml --max-items 3

# 2. Mask -> triage -> review (uses the stub model until a real model is configured)
python -m alert_triage.pipeline --limit 3
```

Output goes to `data/alessa/` (`cases`, `masked`, `tokens`, `results`, `review`). `cases` and
`tokens` are unmasked and are never committed (`data/` is gitignored).

## Configuration

| Where | Key | Meaning |
|-------|-----|---------|
| `.env` | `ALESSA_BASE_URL` | Alessa host (overrides `base_url` in the yaml) |
| `.env` | `MODEL` | `fake` (local) or `apim` |
| `.env` | `APIM_ENDPOINT`, `APIM_KEY`, `MODEL_DEPLOYMENT` | model gateway settings |
| `.env` | `STORAGE`, `BLOB_ACCOUNT_URL` | `local` or `blob` |
| `config/alessa.yaml` | `result_set_id`, `process_id`, `table_name` | the Entity 360 result set |
| `config/alessa.yaml` | `selection` | which work items to pick (state, assignee, module) |
| `config/pii_fields.yaml` | | fields to mask |
| `config/sop/alessa_rules.md` | | the triage business rules |

## Testing

```bash
pytest
```

Tests run against a bundled mock server (`tests/mock_server.py`) that mimics the Alessa data calls,
so no live environment is needed.

## Power Automate alternative

`automation/` contains a Power Automate Desktop version of the extraction that performs the same
read-only calls from a desktop flow. See `automation/README.md`.

## Status / next steps

- Cloud storage (Blob) and the hosted model (APIM / Foundry) are wired but inactive until access is granted.
- `config/sop/alessa_rules.md` and `config/pii_fields.yaml` are placeholders pending the business rules and PII field list.
- Free-text PII detection (for names inside descriptions and comments) is to be added before any real model call.

Internal proof of concept – not for distribution.
