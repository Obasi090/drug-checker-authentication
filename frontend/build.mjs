import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = path.dirname(fileURLToPath(import.meta.url));
const outputDir = path.join(frontendDir, "dist");
const apiBaseUrl = (process.env.DRUG_CHECKER_API_BASE_URL || "").trim().replace(/\/+$/, "");

if (apiBaseUrl) {
  const parsed = new URL(apiBaseUrl);
  if (parsed.protocol !== "https:" && parsed.hostname !== "localhost" && parsed.hostname !== "127.0.0.1") {
    throw new Error("DRUG_CHECKER_API_BASE_URL must use HTTPS outside local development.");
  }
}

await rm(outputDir, { recursive: true, force: true });
await mkdir(outputDir, { recursive: true });
for (const file of ["index.html", "drugChecker.css", "drugChecker.js"]) {
  await cp(path.join(frontendDir, file), path.join(outputDir, file));
}
await writeFile(
  path.join(outputDir, "config.js"),
  `window.DrugCheckerConfig = { apiBaseUrl: ${JSON.stringify(apiBaseUrl)} };\n`,
  "utf8",
);
const html = await readFile(path.join(outputDir, "index.html"), "utf8");
if (!html.includes("config.js") || !html.includes("drugChecker.js")) {
  throw new Error("Frontend HTML is missing its runtime configuration or application script.");
}
console.log(`Built static frontend in ${outputDir}; API URL ${apiBaseUrl ? "configured" : "not configured"}.`);
