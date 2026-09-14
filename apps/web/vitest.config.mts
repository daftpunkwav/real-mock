import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  // tsconfig uses jsx:preserve for Next; the React plugin compiles .tsx for
  // tests so component suites transform instead of leaking raw JSX.
  plugins: [react()],
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
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
