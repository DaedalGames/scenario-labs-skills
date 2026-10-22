#!/usr/bin/env node
// Every SKILL.md ends with the release version it was published with, so an
// agent holding an installed copy can tell it apart from the release the
// Scenario MCP server serves. The stamp is a body comment, not frontmatter:
// Claude Code strips frontmatter before the agent sees the skill.
//
// release-please rewrites the version on every line carrying
// x-release-please-version, through the globbed extra-files entry in
// release-please-config.json, so a release PR updates every stamp at once.
//
//   node scripts/version-stamp.mjs           stamp every SKILL.md with version.txt
//   node scripts/version-stamp.mjs --check   exit 1 if any stamp is missing or stale
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { listSkills } from "./lib/skills.mjs";

process.chdir(path.join(path.dirname(fileURLToPath(import.meta.url)), ".."));

const STAMP_GLOB = "skills/**/SKILL.md";
const stampLine = (version) =>
  `<!-- scenario-skills-version: ${version} x-release-please-version -->`;
const isStampLine = (line) => line.includes("scenario-skills-version:");

const version = readFileSync("version.txt", "utf8").trim();
const expected = stampLine(version);
const check = process.argv.includes("--check");
const errors = [];

for (const { dir } of listSkills()) {
  const file = path.join(dir, "SKILL.md");
  const content = readFileSync(file, "utf8");
  const lines = content.trimEnd().split("\n");
  if (check) {
    const stamps = lines.filter(isStampLine);
    if (stamps.length !== 1 || lines.at(-1) !== expected) {
      errors.push(
        `${file}: must end with exactly one line "${expected}" (found ${stamps.length} version stamps)`,
      );
    }
    continue;
  }
  const body = lines
    .filter((line) => !isStampLine(line))
    .join("\n")
    .trimEnd();
  const stamped = `${body}\n\n${expected}\n`;
  if (stamped !== content) writeFileSync(file, stamped);
}

if (check) {
  const config = JSON.parse(readFileSync("release-please-config.json", "utf8"));
  const extraFiles = config.packages?.["."]?.["extra-files"] ?? [];
  if (
    !extraFiles.some(
      (entry) =>
        entry.type === "generic" && entry.glob && entry.path === STAMP_GLOB,
    )
  ) {
    errors.push(
      `release-please-config.json: extra-files needs { "type": "generic", "path": "${STAMP_GLOB}", "glob": true }, or releases stop updating the stamps`,
    );
  }
  if (errors.length > 0) {
    for (const error of errors) console.error(error);
    console.error("Run `pnpm stamp` to stamp every SKILL.md with version.txt.");
    process.exit(1);
  }
  console.log(`Every SKILL.md carries version stamp ${version}`);
}
