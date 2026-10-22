import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  copyFileSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative } from "node:path";
import test from "node:test";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { listSkills } from "./lib/skills.mjs";
import { STAMP_GLOB, stampLine } from "./version-stamp.mjs";

const scripts = dirname(fileURLToPath(import.meta.url));
const STAMP =
  "<!-- scenario-skills-version: 1.2.3 x-release-please-version -->";
const CONFIG = {
  packages: {
    ".": {
      "extra-files": [
        { type: "generic", path: "skills/**/SKILL.md", glob: true },
      ],
    },
  },
};

// A minimal repository with one core and one expert skill.
function repo(t, { core, expert, config = CONFIG }) {
  const root = mkdtempSync(join(tmpdir(), "skills-stamp-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  for (const file of ["version-stamp.mjs", "lib/skills.mjs"]) {
    mkdirSync(dirname(join(root, "scripts", file)), { recursive: true });
    copyFileSync(join(scripts, file), join(root, "scripts", file));
  }
  const files = {
    core: join(root, "skills/scenario-demo/SKILL.md"),
    expert: join(root, "skills/dcc/demo/scenario-demo-expert/SKILL.md"),
  };
  mkdirSync(dirname(files.core), { recursive: true });
  mkdirSync(dirname(files.expert), { recursive: true });
  writeFileSync(files.core, core);
  writeFileSync(files.expert, expert);
  writeFileSync(join(root, "skills/dcc/demo/README.md"), "");
  writeFileSync(join(root, "version.txt"), "1.2.3\n");
  writeFileSync(
    join(root, "release-please-config.json"),
    JSON.stringify(config),
  );
  const run = (...args) =>
    spawnSync("node", [join(root, "scripts/version-stamp.mjs"), ...args], {
      encoding: "utf8",
    });
  const read = (which) => readFileSync(files[which], "utf8");
  return { run, read };
}

const SKILL = "---\nname: x\n---\n\n# X\n\nBody.\n";

test("stamping appends one stamp to every skill and is idempotent", (t) => {
  const { run, read } = repo(t, { core: SKILL, expert: `${SKILL}\n\n` });
  assert.equal(run().status, 0);
  assert.equal(read("core"), `${SKILL}\n${STAMP}\n`);
  assert.equal(read("expert"), `${SKILL}\n${STAMP}\n`);
  assert.equal(run("--check").status, 0);
  run();
  assert.equal(read("core"), `${SKILL}\n${STAMP}\n`);
});

test("stamping replaces a stale stamp rather than adding a second", (t) => {
  const stale = `${SKILL}\n${STAMP.replace("1.2.3", "1.0.0")}\n`;
  const { run, read } = repo(t, { core: stale, expert: stale });
  run();
  assert.equal(read("core"), `${SKILL}\n${STAMP}\n`);
});

test("stamping keeps prose that mentions the stamp", (t) => {
  const prose = `${SKILL}The scenario-skills-version: comment ends the file.\n`;
  const { run, read } = repo(t, { core: prose, expert: prose });
  run();
  assert.equal(read("core"), `${prose}\n${STAMP}\n`);
});

test("the check accepts a stamp older than version.txt", (t) => {
  const older = `${SKILL}\n${STAMP.replace("1.2.3", "1.1.9")}\n`;
  const { run } = repo(t, { core: older, expert: `${SKILL}\n${STAMP}\n` });
  assert.equal(run("--check").status, 0);
});

test("the check fails on a missing, newer, misplaced, doubled or malformed stamp", (t) => {
  const cases = {
    missing: SKILL,
    newer: `${SKILL}\n${STAMP.replace("1.2.3", "1.10.0")}\n`,
    misplaced: `${STAMP}\n${SKILL}`,
    doubled: `${SKILL}\n${STAMP}\n${STAMP}\n`,
    malformed: `${SKILL}\n<!-- scenario-skills-version: 1.2.3 -->\n`,
  };
  for (const [name, content] of Object.entries(cases)) {
    const { run } = repo(t, { core: `${SKILL}\n${STAMP}\n`, expert: content });
    const result = run("--check");
    assert.equal(result.status, 1, name);
    assert.match(result.stderr, /scenario-demo-expert\/SKILL\.md/, name);
  }
});

test("the check names the newer version it found", (t) => {
  const newer = `${SKILL}\n${STAMP.replace("1.2.3", "2.0.0")}\n`;
  const { run } = repo(t, { core: newer, expert: `${SKILL}\n${STAMP}\n` });
  assert.match(
    run("--check").stderr,
    /stamp 2\.0\.0 is newer than version\.txt 1\.2\.3/,
  );
});

test("the check fails when releases would stop updating the stamps", (t) => {
  const stamped = `${SKILL}\n${STAMP}\n`;
  const { run } = repo(t, {
    core: stamped,
    expert: stamped,
    config: { packages: { ".": {} } },
  });
  const result = run("--check");
  assert.equal(result.status, 1);
  assert.match(result.stderr, /release-please-config\.json/);
});

// release-please's own pinned updater and glob matcher, so a change to the
// stamp format or the layout fails here rather than in a release PR.
const requireFromReleasePlease = createRequire(
  createRequire(import.meta.url).resolve("release-please"),
);
const { Generic } = requireFromReleasePlease("./updaters/generic.js");
const { Version } = requireFromReleasePlease("./version.js");
const { Minimatch } = createRequire(
  requireFromReleasePlease.resolve("@google-automations/git-file-utils"),
)("minimatch");

test("release-please rewrites the stamp and nothing else", () => {
  const before = `${SKILL}Version 1.2.3 in prose stays.\n\n${stampLine("1.2.3")}\n`;
  const updater = new Generic({ version: Version.parse("1.3.0") });
  assert.equal(
    updater.updateContent(before),
    before.replace(stampLine("1.2.3"), stampLine("1.3.0")),
  );
});

test("the release-please glob reaches every skill, expert tools included", () => {
  const config = JSON.parse(
    readFileSync(join(scripts, "../release-please-config.json"), "utf8"),
  );
  assert.ok(
    config.packages["."]["extra-files"].some(
      (entry) => entry.path === STAMP_GLOB && entry.glob,
    ),
  );
  const glob = new Minimatch(STAMP_GLOB);
  const root = join(scripts, "..");
  const skills = listSkills(join(root, "skills"));
  for (const category of ["dcc", "game-engines"]) {
    assert.ok(skills.some((skill) => skill.dir.includes(`/${category}/`)));
  }
  for (const { dir } of skills) {
    const file = `${relative(root, dir)}/SKILL.md`;
    assert.ok(glob.match(file), file);
  }
});
