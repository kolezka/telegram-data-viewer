#!/usr/bin/env bun
/**
 * Fetches /openapi.json from a running FastAPI dev server (default 127.0.0.1:5000)
 * and writes typed interfaces to ./src/api/types.ts.
 *
 * Usage:
 *   bun run codegen                       # default URL
 *   bun run codegen http://host:port      # override
 */
import { spawn } from "bun";

const url = process.argv[2] ?? "http://127.0.0.1:5000/openapi.json";

console.log(`Fetching ${url}...`);
const res = await fetch(url);
if (!res.ok) {
  console.error(`Failed: ${res.status} ${res.statusText}`);
  console.error("Is the FastAPI server running? Try: cd .. && (cd api && python3 -m webui api/tests/fixtures/mini-parsed)");
  process.exit(1);
}
const schema = await res.text();

const tmpFile = "/tmp/tg-viewer-openapi.json";
await Bun.write(tmpFile, schema);

console.log(`Running openapi-typescript...`);
const proc = spawn(["bunx", "openapi-typescript", tmpFile, "-o", "src/api/types.ts"], {
  stdout: "inherit",
  stderr: "inherit",
});
const exitCode = await proc.exited;
if (exitCode !== 0) {
  console.error(`openapi-typescript exited ${exitCode}`);
  process.exit(exitCode);
}

console.log("Wrote src/api/types.ts");
