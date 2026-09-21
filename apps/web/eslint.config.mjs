// ESLint 9 flat config (Next.js official migration path).
// eslint-config-next 15.5 is still legacy .eslintrc; wrap with FlatCompat.
// See https://nextjs.org/docs/app/api-reference/config/eslint#migrating-existing-config
import { FlatCompat } from "@eslint/eslintrc";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const compat = new FlatCompat({ baseDirectory: __dirname });

const eslintConfig = [
  // Skip build artifacts and dependencies
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "out/**",
      "coverage/**",
      "next-env.d.ts",
      "vitest.config.mts",
      "public/**",
      // Generated OpenAPI types: do not hand-edit or review
      "src/types/generated/**",
    ],
  },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "@/lib/api/apiService",
              message: "Use profileHttp (@/lib/api/clients)",
            },
            {
              name: "@/lib/api/agentService",
              message: "Use prepCoachHttp (@/lib/api/clients)",
            },
            {
              name: "@/lib/api/interviewService",
              message: "Use interviewHttp (@/lib/api/clients)",
            },
          ],
        },
      ],
    },
  },
];

export default eslintConfig;
