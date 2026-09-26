# The engagement-document schema — versioning discipline (PLAN-v3 3.4)

**The artefacts:** `engagement-v1.json` (JSON Schema draft 2020-12, `$id` =
`kessler/engagement/v1`) is the **published interop contract**: a client's own tooling can
validate and consume Kessler engagement documents with any JSON Schema validator, without
importing Python. `examples/engagement-sample.json` is the round-trip fixture — a document
that satisfies the contract it demonstrates.

**The authority is the code, not the schema.** `kessler/schema.py` is the validator the
product runs: it re-asserts C-1 on load (an unevidenced success cannot be constructed or
loaded) — a guarantee no JSON Schema can express. The published schema MIRRORS the code;
where the two ever disagree, the schema is wrong and gets fixed. The drift guard in
`tests/test_schema.py` makes silent disagreement impossible: it compares the schema file's
`$id`, required sets, and enums against the code's constants on every test run.

## The rules (borrowed discipline, named sources)

| # | Rule | Where kessler enforces it | Provenance |
| --- | --- | --- | --- |
| 1 | The version is stamped IN the document (`"schema": "kessler/engagement/vN"`), never inferred | `parse()` refuses any other value | inspect_ai stamps `eval` metadata; CSAF carries `version` per document |
| 2 | Unknown schema ids are REFUSED, not best-effort parsed | `schema.py:327-331` ("refusing to best-effort parse a document this code does not know"); tested at `test_schema.py:201` | inspect_ai `_log.py` raises on newer `schema_version` |
| 3 | Unknown KEYS are drift = refuse; missing keys are gaps = refuse | `_keys()` exact key-set enforcement everywhere | same philosophy as kessler's lint fail-closed rules |
| 4 | A new version is ADDITIVE-ONLY over v1's frozen text: v2 files are added ALONGSIDE, v1 is never edited | this directory: `engagement-v1.json` frozen at release; `engagement-v2.json` will sit beside it | C-9 (never rewrite history — supersede); CSAF publishes per-version schema URLs |
| 5 | A validator registry, not a mutable validator: `parse_v1` + `parse_v2` dispatch on the stamp | when v2 ships, `parse(doc)` routes on `doc["schema"]`; today there is exactly one entry | inspect_ai keeps readers for older logs; SARIF consumers key on `$schema` |
| 6 | The published schema is normative for shape; the code is normative for semantics (C-1, KES contract) | drift guard keeps the halves equal on shape only | SARIF's `$schema` + spec text; our schema description fields say so explicitly |

## Versioning a document means (the day a field is added)

1. Add `engagement-v2.json` with the new field; freeze v1 forever.
2. Register `parse_v2` beside `parse_v1`; `parse()` dispatches on the stamp. Old documents
   stay byte-valid and re-reportable (C-9: a delivered engagement never mutates).
3. The drift guard parameterises over `(SCHEMA_ID_vN, file_vN)` pairs; the round-trip test
   runs per version.
4. The report generator may render v1 and v2 documents identically — additive fields may
   not change existing numbers (the measurement contract, AGENTS.md).

## What clients may assume

- Every document `kessler save` writes validates against the file named by its own
  `schema` field.
- `kessler validate <doc>` is the product's verdict; a JSON Schema pass alone is NOT
  acceptance (shape-valid ≠ C-1-valid — the validator re-asserts evidence on load).
- A document whose `schema` field this tool does not know is an error to route to
  Kessler, never a thing to guess at.
