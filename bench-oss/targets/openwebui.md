# BENCH-OSS-01 — Open WebUI (self-hosted)

- **Source:** https://github.com/open-webui/open-webui (image `ghcr.io/open-webui/open-webui:main`)
- **Pinned digest:** `sha256:8b432fe0a65b91116afc7961365c6cca5379cc923171386a96691f3471f3cae9`
- **Licence:** "Open WebUI License" (custom, BSD-3-style with a branding clause; GitHub reports
  SPDX `NOASSERTION`). We run an unmodified, unredistributed, self-hosted copy: the licence's
  redistribution/branding conditions are not engaged; running our own instance is standard use.
- **Deployed:** 2026-10-02, `/opt/bench-oss` compose project, loopback `:8101`, model via the
  lab endpoint (qwen3.8-flash), auth enabled with an instance-local account (credentials live
  on the host only), no tools enabled: the chat surface is the whole scope.
- **Measured:** BENCH-OSS-01, automated-oracle corpus subset, 4 lanes, loopback, run
  `out/oss-openwebui.json` (registered in `bench-register.json`).
- **Authorization:** `{"kind": "ownership"}` — the measured system is our own deployed
  instance on our own host. No third-party system, hosted service, or data is touched. The
  project's own cloud offering is untouched.
- **ToS check:** for a self-hosted copy the governing terms are the open licence above plus
  our hosting provider's acceptable-use terms (no violation: private research instance, no
  service to third parties).
