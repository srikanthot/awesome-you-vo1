# Power Automate Desktop extraction (read-only)

The same read-only extraction as `alert_triage.extractor`, run from a Power Automate Desktop (PAD)
flow. PAD drives the Edge window where the analyst is signed in to Alessa and runs
`alessa_extract.js` inside the page. The script performs Alessa's own read calls and returns one
JSON document with a case package per work item.

## Prerequisites
- Power Automate Desktop installed, with the Microsoft Power Automate extension enabled in Edge.
- The analyst signed in to Alessa in Edge, on the Entity 360 work items page.

## Flow (5 actions)
| # | PAD action | Settings |
|---|------------|----------|
| 1 | Set variables | `MaxItems`, `LookbackDays`, `ResultSetId`, `ProcessId`, `ResultSetTable`, `OutputFolder` |
| 2 | Attach to running Microsoft Edge | By title = `Alessa` -> `Browser` |
| 3 | Run JavaScript function on web page | Instance `%Browser%`; function: the whole of `alessa_extract.js` -> `Result` |
| 4 | Convert JSON to custom object (optional) | `%Result%` -> `Cases` (e.g. log `%Cases.count%`) |
| 5 | Write text to file | `%OutputFolder%\cases_%CurrentDateTime%.json`; Text `%Result%` |

PAD substitutes `%MaxItems%`, `%LookbackDays%`, `%ResultSetId%`, `%ProcessId%` and
`%ResultSetTable%` into the script from the flow variables.

## Notes
- **Read-only:** the script can only send the read calls in its allow-list. Writes are not possible from it.
- **Synchronous calls:** it uses synchronous requests on purpose, because the PAD JavaScript action
  returns before promises resolve. One run of a few work items takes a few seconds.
- **Session expiry:** if the session has expired the script throws "session expired"; sign in and rerun.
- **Unmasked output:** the result contains personal data. Keep the file internal and send it to the
  masking step before any model call.
