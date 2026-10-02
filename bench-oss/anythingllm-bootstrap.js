// bench-oss: bootstrap a workspace + developer API key for the measurement harness.
// Single-user mode. Never prints the key; writes it to storage/bench-api-key.txt (0600-ish).
process.chdir("/app/server");
const { PrismaClient } = require("@prisma/client");
const crypto = require("crypto");
const fs = require("fs");
const prisma = new PrismaClient();

(async () => {
  let ws = await prisma.workspaces.findFirst({ orderBy: { id: "asc" } });
  if (!ws) {
    ws = await prisma.workspaces.create({ data: { name: "bench", slug: "bench" } });
  }
  let key = await prisma.api_keys.findFirst({ orderBy: { id: "asc" } });
  const created = !key;
  if (!key) {
    key = await prisma.api_keys.create({
      data: { name: "bench-oss", secret: crypto.randomUUID() },
    });
  }
  const settings = {};
  for (const row of await prisma.system_settings.findMany()) {
    settings[row.label] = row.value;
  }
  fs.writeFileSync("/app/server/storage/bench-api-key.txt", key.secret, { mode: 0o600 });
  console.log(JSON.stringify({
    slug: ws.slug,
    keyCreated: created,
    keyLen: key.secret.length,
    llmProvider: settings["llm_provider"] || null,
    hasGenericBase: Boolean(settings["generic_open_ai_base_path"]),
    settingCount: Object.keys(settings).length,
  }));
})().catch((e) => { console.error("BOOTSTRAP FAIL:", e.message); process.exit(1); });
