# RealMock API

FastAPI 后端,打包为 `realmock` 包(src layout),以 editable 方式安装。

## 运行

```bash
# 仅首次需要
pip install -e ./apps/api

# 之后启动(无需 PYTHONPATH)
python -m uvicorn realmock.asgi:app --host 127.0.0.1 --port 8081
```

本地开发保持单 worker:简历深度评价并发上限按进程计,`--workers N` 会将其放大 N 倍。

## 测试

```bash
cd apps/api && pytest
```

测试布局见 [tests/README.zh.md](tests/README.zh.md)。

## 包结构

`realmock` 包是模块化单体:一个 FastAPI 进程,由共享的平台内核与相互独立的业务域组装而成。结构图见 [src/realmock/README.zh.md](src/realmock/README.zh.md)。
