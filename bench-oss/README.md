# bench-oss — the Open Bench v0 self-hosted OSS builds (PLAN-v5 #22)

Independently-owned instances of third-party open-source AI builds, deployed on our own host
and measured over loopback with the frozen Open Bench method (automated-oracle subset of the
composed corpus, 4 lanes, Wilson intervals, tester named, loopback only). Nothing here ever
touches a third party's system: every measured target is a copy we deployed ourselves.

Launch a measurement: `python scripts/launch-bench-oss.py` (ships scopes, starts the runs on
the host, detached). Register a finished run:

    python -m kessler.cli bench out/oss-<name>.json --ref BENCH-OSS-0N \
        --target-kind oss-selfhosted --authorization '{"kind":"ownership"}'

## The builds

| Unit | Build | Image (pinned) | Endpoint (loopback) | Licence |
| --- | --- | --- | --- | --- |
| BENCH-OSS-01 | Open WebUI | `ghcr.io/open-webui/open-webui@sha256:8b432fe0a65b91116afc7961365c6cca5379cc923171386a96691f3471f3cae9` | `:8101` `/api/chat/completions` | Open WebUI License (custom, BSD-3-style; GitHub metadata: NOASSERTION) |
| BENCH-OSS-02 | AnythingLLM | `mintplexlabs/anythingllm@sha256:f26f30df46916b6e953e3a47ca98f48817726e3df635e62d4bfdd133292ecfff` | `:8102` `/api/v1/openai/chat/completions` | MIT |
| BENCH-OSS-03 | LiteLLM proxy | `ghcr.io/berriai/litellm@sha256:f63fb81b831b170ec16851e23c36ac5bf52ef106b271406429524a2ed730bbfd` | `:8103` `/v1/chat/completions` | MIT outside `enterprise/` (multi-part LICENSE; GitHub chip: NOASSERTION) |

Per-target records (deploy notes, authorization reasoning, ToS/law notes) live in
`targets/` beside this file. The courtesy-notification draft for maintainers lives in
`targets/NOTIFICATION-DRAFT.md` (self-hosted copies run under their open licences; the note
is courtesy, and an objection would drop the unit).

## Deployment notes

- Everything is loopback-only (`127.0.0.1`); the model endpoint is injected at deploy time by
  `deploy.sh` from the honeypot env and never appears in this repo.
- Keys for the harness live on the host at `/opt/bench-oss/keys.env` (0600), never here.
- AnythingLLM runs with `cap_add: SYS_ADMIN` per its upstream deployment docs; noted in its
  target record.
- `anythingllm-bootstrap.js` creates the single-user workspace + a developer API key inside
  the container (its own Prisma client); it never prints the key.
