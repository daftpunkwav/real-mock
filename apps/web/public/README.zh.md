# public/

站点根路径下的静态资源(Next.js `public/` 约定)。

| 路径 | 内容 |
| --- | --- |
| [`avatars/`](avatars/) | 面试官数字人模型(`.glb`),出处见下 |
| `scenes/` | 面试房场景背景(SVG) |
| `vendor/skulpt/` | 浏览器内 Python 代码运行器使用的 Skulpt 发行文件 |
| `avatar-test.html` | 独立的数字人调试页 |

## 数字人模型出处

下表是各文件内嵌 glTF `asset` 元数据记录的来源(读自 `.glb` 的 JSON
chunk);仓库没有随附独立的许可文件。

| 文件 | 来源(内嵌元数据) |
| --- | --- |
| `gentle_female.glb`、`young_female.glb` | [Ready Player Me](https://readyplayer.me)(`generator` / `copyright: "Ready Player Me"`) |
| `hr_female.glb` | [Avaturn](https://avaturn.me),经 Blender 导出(`generator: "Avaturn.me \| Blender"`) |
| `professional_male.glb` | Blender 导出(Khronos glTF Blender I/O v5.0.21);文件与仓库均未记录上游模型来源 |
| `senior_male.glb` | Blender 导出(Khronos glTF Blender I/O v5.0.21);文件与仓库均未记录上游模型来源 |

原始下载时适用的服务条款(Ready Player Me、Avaturn)未随仓库分发——在
本项目之外再分发这些模型前,请先核对相应条款。
