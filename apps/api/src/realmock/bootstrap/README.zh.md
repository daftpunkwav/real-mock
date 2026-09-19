# bootstrap/

进程引导助手(组合根):必须同时知晓 platform 与 domains 的装配逻辑,因此不能放进 `platform/` — platform → domain 的 import 是架构违规。

| 模块 | 用途 |
| --- | --- |
| `db_bootstrap.py` | 聚合入口的数据库引导(双库布局);建表前注册业务 ORM |
| `sessions_orm.py` | `sessions.db` 的域注册:导入所选会话域模型(prep / interview / records / growth)并在 `create_all` 前汇总各域列级 DDL |

`register_sessions_domain_models(domains=...)` 控制哪些业务包注册自己的 ORM,域独立启动时不必加载无关模型。
