# i18n/

语言体系(zh-CN / en)。

| 模块 | 用途 |
| --- | --- |
| `LocaleProvider.tsx` / `localeContext.ts` | 语言状态;文档标题由此渲染,不写 `document.title` |
| `storage.ts` | 语言持久化(localStorage + cookie 双写) |
| `locales.ts` / `resolve.ts` | 语言清单与解析;测试须经 `@/i18n/resolve` 解析,不直接 import `.tsx` |
| `catalog.ts` | 消息 catalog 的类型与查找 |
| `messages/` | 按语言的 catalog(`zh-CN/`、`en/`)— 唯一允许存放用户可见文案的位置 |
| `errors.ts` | `NET` 族错误码 → 文案映射 |
| `format.ts` | 语言感知的格式化助手 |
| `LocaleToggle.tsx` | 语言循环切换控件 |
| `localeInitScript.ts` | 注入文档的水合前语言引导脚本 |
