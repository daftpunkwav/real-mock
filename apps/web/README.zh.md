# RealMock web

Next.js + React 前端。dev server 运行在 8080 端口,必须保持 dev 模式(`npm run dev`);生产构建不是本地运行该应用的受支持方式。

## 命令

| 命令 | 用途 |
| --- | --- |
| `npm run dev` | 在 8080 端口启动 dev server |
| `npm run build` | 生产构建(CI 使用;本地开发用 `npm run dev`) |
| `npm run test` | 运行一次 vitest |
| `npm run test:watch` | watch 模式运行 vitest |
| `npm run lint` | ESLint |
| `npm run generate:api-types` | 从后端 OpenAPI 契约再生成 `src/types/generated/api.d.ts` |

`generate:api-types` 先运行 `../../scripts/export_openapi.py`,再对根目录 `openapi.json` 运行 `openapi-typescript`。不要手工编辑 `src/types/generated/`。

## 源码结构(`src/`)

| 目录 | 用途 |
| --- | --- |
| [`app/`](src/app/README.zh.md) | Next.js App Router 页面,每页一个路由段 |
| `features/` | feature 优先的业务模块(见 [src/features/README.zh.md](src/features/README.zh.md)) |
| [`components/`](src/components/README.zh.md) | 跨 feature 的展示组件 |
| [`config/`](src/config/README.zh.md) | 静态前端配置(导航、页面布局、面试阶段、prep 快捷提示) |
| [`lib/`](src/lib/README.zh.md) | 无框架依赖的工具:API client、code runner、compaction、clipboard 等 |
| [`i18n/`](src/i18n/README.zh.md) | 语言体系(zh-CN / en):provider、catalog、错误码映射 |
| [`types/`](src/types/README.zh.md) | 共享类型;`generated/` 存放 OpenAPI 派生的 API 类型 |

## 约定

- 所有用户可见文案来自 i18n catalog;硬编码文案按审查失败处理。
- `config/phases.ts` 镜像后端阶段 SSOT(`realmock.domains.interview.workflows`);后端测试 `tests/interview/test_phase_ssot.py` 保持两者对齐 — 阶段 id 不手工编辑。
- 测试放在所覆盖代码旁的 `__tests__/`。
