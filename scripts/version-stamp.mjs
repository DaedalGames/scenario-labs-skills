#!/usr/bin/env node
// Every SKILL.md ends with the release version it was published with, so an
// agent holding an installed copy can tell which release it comes from. The
// stamp is a body comment, not frontmatter: Claude Code strips frontmatter
// before the agent sees the skill.
//
// release-please rewrites the version on every line carrying
// x-release-please-version, through the globbed extra-files entry in
// release-please-config.json, so a release PR updates every stamp at once.
//
// The check accepts any version up to version.txt, not only an equal one:
// main does not require branches to be up to date, so a skill stamped before
// a release can merge after it, and the next release PR rewrites it anyway.
//
//   node scripts/version-stamp.mjs           stamp every SKILL.md with version.txt
//   node scripts/version-stamp.mjs --check   exit 1 if a stamp is missing, misplaced or newer
import { readFileSync, realpathSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { listSkills } from "./lib/skills.mjs";

export const STAMP_GLOB = "skills/**/SKILL.md";
export const stampLine = (version) =>
  `<!-- scenario-skills-version: ${version} x-release-please-version -->`;
// The whole line, so prose that mentions the stamp is never taken for one.
export const STAMP_PATTERN =
  /^<!-- scenario-skills-version: (\d+)\.(\d+)\.(\d+) x-release-please-version -->$/;

const semver = (match) => match.slice(1, 4).map(Number);
const shorten = (line) => (line.length > 80 ? `${line.slice(0, 77)}...` : line);
const newer = (a, b) => {
  const i = a.findIndex((part, n) => part !== b[n]);
  return i >= 0 && a[i] > b[i];
};

function main() {
  process.chdir(path.join(path.dirname(fileURLToPath(import.meta.url)), ".."));
  const version = readFileSync("version.txt", "utf8").trim();
  const current = version.split(".").map(Number);
  const check = process.argv.includes("--check");
  const errors = [];

  for (const { dir } of listSkills()) {
    const file = path.join(dir, "SKILL.md");
    const content = readFileSync(file, "utf8");
    const lines = content.trimEnd().split("\n");
    if (!check) {
      const body = lines
        .filter((line) => !STAMP_PATTERN.test(line))
        .join("\n")
        .trimEnd();
      const stamped = `${body}\n\n${stampLine(version)}\n`;
      if (stamped !== content) writeFileSync(file, stamped);
      continue;
    }
    const stamps = lines.filter((line) => STAMP_PATTERN.test(line));
    const last = lines.at(-1).match(STAMP_PATTERN);
    if (stamps.length !== 1 || !last) {
      errors.push(
        `${file}: must end with one line "${stampLine(version)}" (found ${stamps.length} stamp lines; last line: "${shorten(lines.at(-1))}")`,
      );
    } else if (newer(semver(last), current)) {
      errors.push(
        `${file}: stamp ${semver(last).join(".")} is newer than version.txt ${version}`,
      );
    }
  }

  if (!check) return;
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
  console.log(`Every SKILL.md carries a version stamp up to ${version}`);
}

// realpath: a temporary directory on macOS is reached through a symlink, and
// import.meta.url is always the resolved path.
if (realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) main();
