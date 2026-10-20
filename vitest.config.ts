import { defineConfig } from "vitest/config";

// Shared config so a bare `vitest run <dir>` (scripts/test-skill-scripts.sh)
// and a developer running `pnpm exec vitest` locally pick up the same
// coverage settings. Coverage only activates with --coverage; this file
// just decides the provider, reporter, and report location.
export default defineConfig({
  test: {
    coverage: {
      provider: "v8",
      reporter: ["cobertura"],
      reportsDirectory: "coverage/ts",
      // Only report the modules a suite actually imports. tests/<name>/
      // suites each cover one skill's slice of code, so reporting every
      // untouched .js in the repo would dilute the percentage with files
      // no suite claims to exercise (see AGENTS.md "Layout").
      all: false,
    },
  },
});
