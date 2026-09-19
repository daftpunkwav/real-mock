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
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
});
