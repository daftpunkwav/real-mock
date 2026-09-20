import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  // tsconfig sets jsx:preserve for Next; under vitest the React plugin is
  // what transforms JSX, so the include must cover .tsx test suites too.
  plugins: [react()],
  test: {
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
    // React 19 exposes act only in development builds. Vitest otherwise defaults
    // to NODE_ENV=production, causing renderHook to fail with a missing React.act.
    env: {
      NODE_ENV: "development",
    },
    coverage: {
      provider: "v8",
      // Regression gates, set just under the measured level so normal churn
      // cannot silently drop coverage (run via `npm test`, which enables
      // coverage). Raise them as coverage grows.
      thresholds: {
        statements: 50,
        branches: 47,
        functions: 47,
        lines: 50,
      },
    },
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
});
