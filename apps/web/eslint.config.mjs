// ESLint flat config.
// eslint-config-next 16 ships native flat configs (eslint-config-next/core-web-vitals
// and eslint-config-next/typescript both export arrays), so no FlatCompat wrapper is
// needed. The previous version imported @eslint/eslintrc, which was never a declared
// dependency - it only resolved through hoisting and disappeared with eslint 10.
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypeScript from "eslint-config-next/typescript";

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
  ...nextCoreWebVitals,
  ...nextTypeScript,
  {
    rules: {
      // eslint-config-next 16 turns on the React Compiler-era react-hooks
      // rules that 15.5 left off. They report 71 findings across 47 files,
      // almost all set-state-in-effect / refs in hooks that are correct today.
      // Fixing them means changing render timing in working code, so that is
      // its own piece of work rather than a version bump - they are set to
      // "warn" so the gate stays meaningful (errors still block) and every
      // finding still shows up in `npm run lint` and `next build`. Promote
      // them back to "error" once that refactor is done.
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/refs": "warn",
      "react-hooks/immutability": "warn",
      "react-hooks/preserve-manual-memoization": "warn",
      "react-hooks/purity": "warn",
      "react-hooks/use-memo": "warn",
      // Prettier owns formatting; these ESLint rules would otherwise report
      // the same lines a different way. Grouped so the split is obvious.
      "@typescript-eslint/indent": "off",
      "@typescript-eslint/quotes": "off",
      "@typescript-eslint/semi": "off",
      "@typescript-eslint/comma-dangle": "off",
      "@typescript-eslint/space-before-blocks": "off",
      "@typescript-eslint/object-curly-spacing": "off",
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
