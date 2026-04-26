#!/usr/bin/env bun
import { rmSync, existsSync } from "fs";

if (existsSync("./dist")) {
  rmSync("./dist", { recursive: true });
}

console.log("Building Tailwind CSS...");
const css = Bun.spawn(["bunx", "tailwindcss", "-i", "./src/styles.css", "-o", "./src/styles.generated.css", "--minify"], {
  stdout: "inherit",
  stderr: "inherit",
});
await css.exited;

console.log("Building JS bundle...");
const result = await Bun.build({
  entrypoints: ["./index.html"],
  outdir: "./dist",
  minify: true,
  splitting: true,
  target: "browser",
});

if (!result.success) {
  for (const message of result.logs) console.error(message);
  process.exit(1);
}

console.log(`Built ${result.outputs.length} files into ./dist/`);
