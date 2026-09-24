# prep/agents/tools/

prep agent 的工具面:声明、注册表装配与五个工具族。上层地图见
[../README.zh.md](../README.zh.md);通用循环与 `ToolSpec` 原语在
`platform/capabilities/ai/agent/tools/`。

## 装配

| 模块 | 职责 |
| --- | --- |
| `spec.py` | 唯一的 `ToolSpec` 形状(function-calling schema + handler)、加载分层与每工具默认超时;叶子工具模块只依赖本文件(外加 `platform/services`)——这里不放 handler 逻辑 |
| `registry.py` | 唯一知道完整工具集的地方:把各族 `SPECS` 列表一次性拼接为 `TOOL_REGISTRY` / `SECONDARY_TOOLS` / `DOMAIN_TOOL_DEFINITIONS`,应用集中式每工具超时表,并向每个 schema 注入模型可覆盖的 `timeout_seconds` 参数。任何叶子模块都不在导入期引用它 |

## 工具族

| 目录 | 工具 | 说明 |
| --- | --- | --- |
| `basic/` | `code_exec`(沙箱代码验证)、`company_info`(目标公司面试风格)、`quiz`(练习提问)、`take_note`(把轮次结论写入工作记忆)、`web_search`、`web_fetch`(读取单页正文) | 每轮核心能力;`web_fetch` 按需加载 |
| `candidate/` | `profile`、`resume` + `shared.py` | 候选人数据检视,每次调用实时 ORM 绑定,绝不跨调用缓存 |
| `memory/` | `write`(持久、幂等)、`list_summaries`、`list_tags`、`get_detail` | 长期记忆访问;索引查询每回合都声明,仅全文详情按需加载 |
| `repo/` | `github.py` | 六个工具共用一个工厂(基于平台 GitHub specs 外加一个 repo 交流工具);按需加载 |
| `system/` | `availability`(轮初按名字门控的静态子集策略)、`compact`(agent 主动压缩;只声明、有意不加载)、`search_tools`(对二级目录按需发现,轮中惰性加载 schema) | 管理工具集自身的元工具 |

测试:`apps/api/tests/prep/`。
