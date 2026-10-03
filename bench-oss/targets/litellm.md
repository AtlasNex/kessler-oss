# BENCH-OSS-03 — LiteLLM proxy (self-hosted)

- **Source:** https://github.com/BerriAI/litellm (image `ghcr.io/berriai/litellm`, tag `main-stable`)
- **Pinned digest:** `sha256:f63fb81b831b170ec16851e23c36ac5bf52ef106b271406429524a2ed730bbfd`
- **Licence:** MIT outside `enterprise/` (verified from the repo LICENSE file text itself;
  GitHub's SPDX chip says NOASSERTION because the file is multi-licence — the proxy image is
  entirely within the MIT portion). Enterprise directory not used.
- **Deployed:** 2026-10-03, `/opt/bench-oss` compose project, loopback `:8103`, upstream model
  injected by `deploy.sh` from the honeypot env (lab endpoint, qwen3.8-flash) via
  `os.environ/` interpolation in `litellm-config.yaml`; master-key Bearer auth on; the native
  OpenAI-compatible surface (`/v1/chat/completions`, model name `qwen3.8-flash`) is the
  measured endpoint.
- **Candidate filter fit (documented session-28 filter: OpenAI-shaped + headless):** the
  serving/gateway layer was chosen deliberately — BENCH-OSS-01 covers the chat UI shape and
  BENCH-OSS-02 the RAG workspace shape; the third shape in an agentic estate is the LLM
  gateway. LiteLLM is headless (config-file deployment), natively OpenAI-shaped, so the
  kernel driver semantics stay identical across all three units (like-for-like ASR).
- **Rejected candidates recorded (licence/shape gate, do not re-litigate):** Flowise
  (repo ARCHIVED + custom licence, NOASSERTION), Dify (NOASSERTION), Langflow (MIT but no
  native chat-completions server route — only /run/{flow} + Responses-style; would have
  required a per-target kernel mutation, breaking like-for-like driver semantics).
- **Measured:** BENCH-OSS-03, automated-oracle corpus subset, 4 lanes, loopback, run
  `out/oss-litellm.json` (registered in `bench-register.json`).
- **Authorization:** `{"kind": "ownership"}` — our own deployed instance on our own host;
  MIT terms permissive for this use; no third-party system or data touched (the upstream
  lab endpoint is ours; its keys ride container env only, never printed or committed).
- **Note:** `drop_params: true` is set in the config (driver `temperature` passes through;
  anything the upstream refuses is dropped rather than failing the unit). Master key lives
  in `/opt/bench-oss/keys.env` as `LITELLM_KEY` (0600, host only).
