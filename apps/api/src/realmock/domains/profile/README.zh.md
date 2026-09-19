# profile/

候选人档案域。单租户:仅一条档案记录,PUT 全量替换语义。

| 层 | 内容 |
| --- | --- |
| `routes/profile.py` | 档案读取 / 更新端点(挂载于 `/profile`) |
| `services/store.py` | 持久化 |
| `services/contract_guard.py` | 响应契约守卫 |
| `schemas/` | `field_meta.py`(字段元数据)、`required.py`、`tech_domains.py`、`update.py`(PUT 请求体)、`response.py` |

薄域:无 `models/`、`agents/`、生命周期钩子。

测试:`apps/api/tests/profile/`。
