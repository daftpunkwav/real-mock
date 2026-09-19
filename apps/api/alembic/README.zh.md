# alembic/

api 域数据库(`api.db`)的 Alembic 迁移链。在 `apps/api/` 下运行:`alembic upgrade head`。

| 路径 | 用途 |
| --- | --- |
| `../alembic.ini` | Alembic 配置。刻意保持纯 ASCII:alembic 以 locale 编码读取它,非 ASCII 注释在 GBK 环境会出错。数据库 URL 由 `env.py` 注入,此处不存密钥 |
| `env.py` | 将 alembic 接入应用:URL 取自 `get_settings().api_database_url`,`target_metadata = ApiBase.metadata` |
| `script.py.mako` | 生成的迁移脚本模板 |
| `versions/` | 有序迁移脚本(基线列回填、模型档案唯一约束、resume lineage、provider full-url / meta) |

## 职责边界

本链只管理挂在 `ApiBase` 上的表(profile / resume / settings 域,定义于 `realmock.platform.models`)。挂在 `SessionsBase` 上的会话域表(prep / interview / records / growth、WS 租约、限流桶)不在本链内:它们由启动时的 `SessionsBase.metadata.create_all` 建表,列变更走各域的 `column_migrations.py`,由 `realmock.bootstrap.sessions_orm` 汇总。
