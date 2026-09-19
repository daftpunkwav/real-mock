# realmock(包根)

后端是模块化单体:一个 FastAPI 进程,在此组装。

| 入口 | 用途 |
| --- | --- |
| `asgi.py` | ASGI 入口;经平台工厂构建应用 |
| [`bootstrap/`](bootstrap/README.zh.md) | 进程引导:数据库装配(`db_bootstrap.py`)与会话 ORM(`sessions_orm.py`) |

## 结构规则

| 包 | 职责 | 可依赖 |
| --- | --- | --- |
| [`platform/`](platform/README.zh.md) | 平台内核:跨域基础设施(AI / 语音能力、DB、配置、契约、共享服务) | 仅 `platform` |
| [`domains/`](domains/README.zh.md) | 七个业务域 | `platform` + 自身包;禁止依赖其他域 |

依赖方向由 `apps/api/tests/architecture/` 测试套件守护:`test_platform_no_domain_imports.py`(platform 不得 import domains)、`test_domains_no_cross_imports.py`(domains 不得互相 import),以及 DB 边界、分层、暴露面与契约同步守卫。跨域协作经由 platform 服务与契约完成。
