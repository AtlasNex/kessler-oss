# BENCH-OSS-04 — Ollama local model runtime (self-hosted)

- **Source:** https://github.com/ollama/ollama (image `docker.io/ollama/ollama`, tag `latest` pinned)
- **Pinned digest:** `sha256:292ee7945dfc3d5840a181f3ab86fedb1e66703e02c8af98b50f4da56b7e278c`
- **Licence:** MIT (verified from the repo LICENSE file text itself, 04 Oct 2026 — the standard
  MIT grant, "Copyright (c) Ollama").
- **Model:** `qwen2.5:7b-instruct` (Apache-2.0 model licence, Tongyi Qianwen LICENSE) — chosen to
  match the sibling units' lab model family (qwen) so the serving-shape comparison stays
  like-for-like. The model lives in the `ollama-models` volume; `deploy.sh` pulls it idempotently.
- **Deployed:** 2026-10-04, `/opt/bench-oss` compose project, loopback `:8104`; the native
  OpenAI-compatible surface (`/v1/chat/completions`) is the measured endpoint.
- **Candidate filter fit (documented session-28 filter: OpenAI-shaped + headless):** the fourth
  estate shape — BENCH-OSS-01 covers the chat UI, -02 the RAG workspace, -03 the LLM gateway;
  a local model runtime (no UI, no RAG, no gateway middleware) is the shape an offline or
  air-gapped agent estate actually runs on. Headless (container + CLI), natively OpenAI-shaped
  on `/v1/chat/completions`, so the kernel driver semantics stay identical across all four
  units (like-for-like ASR).
- **Rejected candidates recorded (do not re-litigate):** FastMCP and other MCP hosts stay
  rejected on the D-042 seam rule (their native surface is MCP, not chat-completions; measuring
  them would force kernel-harness work outside the bench's like-for-like scope). Flowise / Dify /
  Langflow rejections stand as recorded in `targets/litellm.md`.
- **Authorization:** `{"kind": "ownership"}` — our own deployed instance on our own host; MIT
  terms permissive for this use; no third-party system or data touched. The model weights are
  Apache-2.0, pulled from Ollama's public registry into our own volume.
- **Auth on the endpoint:** VERIFIED 04 Oct 2026: this Ollama build accepts unauthenticated
  requests on `/v1/chat/completions` (no-key probe returned 200 with a completion) — the
  `OLLAMA_API_KEY` env var is NOT enforced by this image. The boundary is the loopback-only
  port binding (`127.0.0.1:8104`), stated here plainly; no auth is claimed on this unit. The
  harness still sends a Bearer key (uniform driver); the endpoint ignores it.
- **Disk note (owner flag):** image 9.37GB + model ~4.7GB on a host at 97%; 2.9GB of dangling
  images + 90MB build cache were reclaimed (safe classes only) before the pull.
