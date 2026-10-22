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
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

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

test("the check fails on a missing, stale, misplaced or doubled stamp", (t) => {
  const cases = {
    missing: SKILL,
    stale: `${SKILL}\n${STAMP.replace("1.2.3", "1.0.0")}\n`,
    misplaced: `${STAMP}\n${SKILL}`,
    doubled: `${SKILL}\n${STAMP}\n${STAMP}\n`,
  };
  for (const [name, content] of Object.entries(cases)) {
    const { run } = repo(t, { core: `${SKILL}\n${STAMP}\n`, expert: content });
    const result = run("--check");
    assert.equal(result.status, 1, name);
    assert.match(result.stderr, /scenario-demo-expert\/SKILL\.md/, name);
  }
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
