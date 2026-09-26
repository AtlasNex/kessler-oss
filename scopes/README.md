# Scope files

A scope file is the **machine-readable half of the authorisation**. The human-readable half is
`templates/scope-document.md`, which the client signs. This file is what the coverage denominator is
computed from, and its SHA-256 is what the engagement document records as `scope_sha256`.

**C-7:** no request leaves the machine against a target without a signed scope on disk. That document is
cited in every finding and in the attestation letter, which is why the hash is computed from the file's
actual bytes rather than typed in.

## Format: JSON (or TOML). Not YAML.

`scope.json` works everywhere. `scope.toml` also works on Python 3.11+ and is nicer to hand-write.
**YAML is deliberately not supported** — there is no YAML parser in the standard library, and constraint
C-2 forbids adding one to the core. See `kessler/scope.py` and `docs/DECISIONS.md` D-018.

- `scopes/example-scope.json` — a complete worked example (fictional).

## Shape

| Key | Required | Notes |
| --- | --- | --- |
| `ref` | yes | Engagement reference |
| `client` | yes | Client entity |
| `window` | yes | `{ "start": "YYYY-MM-DD", "end": "YYYY-MM-DD" }` — the authorised testing period |
| `targets` | yes | Each: `id`, `kind` (`agent`/`mcp_server`/`tool`/`memory`/`model`), `version`, `reaches`, `notes` — `version` feeds the report's "systems + version tested" (REPORT-SPEC §1) |
| `exclusions` | yes | ASI category -> **written reason**. A blank reason is refused |
| `note` | no | Free text for the human signing it |

**There is no `scope_sha256` field, on purpose.** The digest is computed from the file bytes on load, so
it cannot be wrong and cannot be hand-edited. A file claiming its own hash is refused as an unknown key.

## Use

```python
from kessler.scope import load_scope, verify_scope

scope = load_scope("scopes/example-scope.json")
print(scope.scope_sha256[:16], len(scope.targets), len(scope.exclusions))

eng = scope.to_engagement(attempts=my_attempts)   # the engagement this scope authorises
verify_scope(eng, "scopes/example-scope.json")    # re-check later; raises if the file changed
```

`verify_scope` is the check the report linter *cannot* do — it has no file. It is what makes "tested
against a signed scope" something a third party can confirm rather than take on trust.
