# interview/capabilities/

interview 域特有的能力。只被本域消费,因此放在这里而不是
`platform/capabilities/`(那里的能力保持跨域)。上层地图见
[../README.zh.md](../README.zh.md)。

## `rag/` — 公司知识库 RAG

| 模块 | 职责 |
| --- | --- |
| `base.py` | `RAGBackend` 协议:实现它并在工厂注册即可,调用方不变 |
| `factory.py` | 按 `settings.rag_backend` 选择后端:本地 Chroma / stepfun / `none` 占位 |
| `company_rag.py` | 门面;`llm=None` 时退化为空桩(测试用)。显式委托方法,无 `__getattr__` 魔法 |
| `local_backend.py` | 本地 Chroma + 任意 OpenAI 兼容 `/embeddings` 端点 |
| `stepfun_backend.py` | StepFun 托管 `vector_stores`:检索是 OpenAI 协议内置工具类型(无 `/embeddings` 端点) |
| `stepfun_index_http.py` | StepFun 索引的 HTTP 层(创建 / 上传 / 挂载 / 校验);出站流量与其他出口一致走 pinning |
| `_kb_data.py` | 纯数据层(collection 名等共享常量),无业务依赖 |

## `sandbox/`

| 模块 | 职责 |
| --- | --- |
| `evaluator.py` | 现场编程测试评估器与执行桥:用测试用例校验候选人输出、聚合得分、按 WebSocket 协议格式化结果 |

## `vision/`

| 模块 | 职责 |
| --- | --- |
| `agent.py` | `VisionAgent`:把单帧面部分析(是否检测到人脸 / 视线偏离 / 紧张度 / 人脸数)压缩为一句状态行,写入 realtime orchestrator snapshot(`vision_summary`) |

测试:`apps/api/tests/interview/`。
