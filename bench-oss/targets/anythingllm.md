# BENCH-OSS-02 — AnythingLLM (self-hosted)

- **Source:** https://github.com/Mintplex-Labs/anything-llm (image `mintplexlabs/anythingllm`)
- **Pinned digest:** `sha256:f26f30df46916b6e953e3a47ca98f48817726e3df635e62d4bfdd133292ecfff`
- **Licence:** MIT.
- **Deployed:** 2026-10-02, `/opt/bench-oss` compose project, loopback `:8102`, model via the
  lab endpoint through the "Generic OpenAI" provider (qwen3.8-flash); single-user mode with a
  bootstrapped workspace (`bench`) and an instance-local developer API key (host only); the
  native OpenAI-compatible surface (`/api/v1/openai/chat/completions`, model = workspace
  slug) is the measured endpoint.
- **Measured:** BENCH-OSS-02, automated-oracle corpus subset, 4 lanes, loopback, run
  `out/oss-anythingllm.json` (registered in `bench-register.json`).
- **Authorization:** `{"kind": "ownership"}` — our own deployed instance on our own host;
  MIT terms fully permissive; no third-party system or data touched.
- **Note:** `cap_add: SYS_ADMIN` follows the upstream Docker deployment documentation (their
  embedded collectors); it is the documented deployment shape, recorded here deliberately.
