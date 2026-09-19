# settings/

设置域:BYOK 处理器配置、模型能力注册表、连通性测试、第三方集成。

| 层 | 内容 |
| --- | --- |
| `routes/stages.py` | 三阶段处理器配置:`api_base` 格式校验、密钥落库前加密(AES-256-GCM)、识别凭据与推理密钥分离存放 |
| `routes/models.py` | 模型档案 API:provider / channel / model / task 绑定路由(能力声明) |
| `routes/model_tests.py` | 连通性 / 模型测试 |
| `routes/integrations.py` | 第三方集成凭据(GitHub) |
| `services/` | `model_registry.py`、`vendor_apply.py`(应用厂商描述符)、`github_integration.py`、`stage_tests.py`、`validation.py`、`route_timing.py` |

薄域:无 `models/`、生命周期钩子。

测试:`apps/api/tests/settings/`。
