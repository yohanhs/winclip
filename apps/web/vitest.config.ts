import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "happy-dom",
    setupFiles: ["./tests/setup/vitest.ts"],
    globals: true,
    alias: {
      "@": new URL("./", import.meta.url).pathname,
    },
    coverage: {
      provider: "v8",
      reporter: ["text", "html", "lcov"],
      include: ["components/**/*.tsx", "hooks/**/*.ts", "lib/**/*.ts"],
      exclude: ["**/*.test.tsx", "**/*.spec.tsx", "e2e/**"],
    },
    outputFile: "./test-results/unit/",
    pool: "threads",
    poolOptions: {
      threads: {
        maxThreads: 4,
        minThreads: 1,
      },
    },
  },
});