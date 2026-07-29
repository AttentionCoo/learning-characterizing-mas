# LearnAgent 接口文档

> 版本：V3.0
> 核对日期：2026-07-29
> 实现事实源：`backend/server/src/main/java/com/learnagent/controller`、`backend/server/src/main/java/com/learnagent/param`、`model/app/routers`

本文档只记录当前代码中存在的接口。Java 后端共 64 个业务端点，其中 17 个为 SSE；Python 模型层共 17 个内部端点。

## 1. 全局约定

### 1.1 访问地址

| 场景 | 地址 |
|:---|:---|
| Docker 浏览器入口 | `http://127.0.0.1:5173` |
| 浏览器业务 API | 同源 `/api/**`，由 Nginx 转发到后端 |
| 手动启动后端 | `http://127.0.0.1:8080` |
| 手动启动模型层 | `http://127.0.0.1:8000` |

Docker Compose 不向宿主机暴露后端和模型端口。模型接口属于内部接口，不应直接暴露公网。

### 1.2 认证

登录成功后，请在以下任一请求头中携带 Token：

```http
token: <jwt>
Authorization: Bearer <jwt>
```

无需登录：

- `POST /api/user/register`
- `POST /api/user/login`
- `POST /api/user/upload`
- `/uploads/**` 静态文件

`POST /api/user/logOut` 需要有效 Token。模型统一推理入口通过请求体 `token` 字段校验后端签发的内部 JWT。

### 1.3 统一响应

非流式 Java 接口通常返回：

```json
{
  "code": 1,
  "msg": "success",
  "data": {}
}
```

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| `code` | integer | `1` 成功，`0` 业务失败 |
| `msg` | string | 状态或错误说明 |
| `data` | any | 业务数据，可为空 |

HTTP 200 不等于业务成功，调用方仍需检查 `code`。模型层专用路由也可能返回 FastAPI 的标准 HTTP 错误。

### 1.4 SSE 协议

SSE 接口使用 `POST` 和 `Content-Type: text/event-stream`。一个事件示例：

```text
event: token
id: 123:8
data: {"type":"token","content":"增量内容"}
```

| `type` | 处理方式 |
|:---|:---|
| `init` | 保存 `talkId` 或 `taskId`；`newTalk` 表示本次是否新建业务对话 |
| `node_start` | 展示当前推理节点 |
| `thinking` | 展示结构化进度，不等同于模型隐藏思维链 |
| `node_done` | 展示节点摘要和可选证据来源 |
| `token` / `chunk` / `result` | 追加 `content` |
| `replace` | 用完整 `content` 替换此前累计内容，防止最终报告重复 |
| `done` | 流结束；画像场景可能附带 `profile_dimensions` |
| `error` | 读取 `message` 并结束或等待后续 `done` |

业务 SSE 支持 `Last-Event-ID` 时会尝试回放缓存事件。客户端应同时兼容 `token` 和 `chunk`。

### 1.5 分页与时间

- 分页接口按控制器参数使用 `page`、`size`，默认值以代码为准。
- 日期时间字符串按接口当前字段传递，不额外假设时区格式。
- Base64 图片建议使用 `data:image/...;base64,...` 完整 Data URL。

## 2. Java 业务接口总览

| 模块 | 控制器 | 端点 | SSE |
|:---|:---|:---:|:---:|
| 用户、资料与上传 | Login / ChangeKey / InitialPage / Upload | 8 | 0 |
| 学习画像 | ProfileController | 6 | 1 |
| 学习资源 | ResourceController | 15 | 9 |
| 学习路径 | LearningPathController | 9 | 1 |
| 智能辅导 | TutorController | 5 | 2 |
| 学习评估 | AssessmentController | 6 | 1 |
| 代码辅助 | CodeController | 2 | 1 |
| 医学影像 | MedicalController | 7 | 1 |
| 通用对话 | QuesController | 2 | 1 |
| 课程 | CourseController | 2 | 0 |
| 监控 | MonitorController | 2 | 0 |
| **合计** |  | **64** | **17** |

`DocumentController.java` 当前为空，因此没有 `/api/documents/**` 接口。

## 3. 用户与账户

| 方法 | 路径 | 认证 | 说明 |
|:---|:---|:---:|:---|
| POST | `/api/user/register` | 否 | 注册 |
| POST | `/api/user/login` | 否 | 登录并返回 Token |
| POST | `/api/user/logOut` | 是 | 登出并清理 Token |
| GET | `/api/user/showInfo` | 是 | 获取当前用户资料 |
| PUT | `/api/user/showInfo/changeKey` | 是 | 修改密码、头像、专业、年级和专长 |
| GET | `/api/user/title` | 是 | 获取通用对话标题列表 |
| DELETE | `/api/user/deleteTalk/{talk_id}` | 是 | 删除通用对话 |
| POST | `/api/user/upload` | 否 | Multipart 上传文件，字段名 `file` |

注册/登录请求：

```json
{
  "name": "student01",
  "password": "your-password",
  "image": "/images/default.png"
}
```

资料修改请求可包含：

```json
{
  "prePassword": "old-password",
  "newPassword": "new-password",
  "image": "https://example/avatar.png",
  "major": "临床医学",
  "grade": "大三",
  "specialty": "神经病学"
}
```

## 4. 学习画像

| 方法 | 路径 | SSE | 说明 |
|:---|:---|:---:|:---|
| POST | `/api/profile/conversation` | 是 | 画像对话并在结束后异步更新画像 |
| GET | `/api/profile` | 否 | 获取当前用户最新画像 |
| PUT | `/api/profile/dimensions` | 否 | 合并更新画像维度 |
| GET | `/api/profile/conversation/{talkId}` | 否 | 获取指定画像对话历史 |
| GET | `/api/profile/conversations` | 否 | 获取画像对话列表 |
| DELETE | `/api/profile/conversation/{talkId}` | 否 | 删除画像对话 |

画像对话请求：

```json
{
  "talkId": "123",
  "message": "我是临床医学大三学生，想加强脑卒中影像判读",
  "images": []
}
```

规则：

- 传入有效且属于当前用户的画像 `talkId` 时继续原对话。
- `talkId` 为空、无效或类型不匹配时，业务对话接口会新建画像对话并通过 `init.newTalk=true` 告知客户端。
- 画像维度抽取复用本次画像对话历史，不创建额外的“画像生成”对话。

画像维度键：`knowledgeBase`、`cognitiveStyle`、`learningGoal`、`errorPattern`、`learningPace`、`resourcePreference`、`clinicalExperience`、`emotionState`。

## 5. 学习资源

| 方法 | 路径 | SSE | 说明 |
|:---|:---|:---:|:---|
| POST | `/api/resources/generate` | 是 | 通用资源生成入口，一次只能指定一种类型 |
| POST | `/api/resources/generate/document` | 是 | 课程讲解文档 |
| POST | `/api/resources/generate/mindmap` | 是 | 思维导图 |
| POST | `/api/resources/generate/quiz` | 是 | 练习题 |
| POST | `/api/resources/generate/reading` | 是 | 指南与拓展阅读 |
| POST | `/api/resources/generate/case-study` | 是 | 临床案例 |
| POST | `/api/resources/generate/plan` | 是 | 学习方案 |
| POST | `/api/resources/generate/code-practice` | 是 | Python 代码实操 |
| POST | `/api/resources/generate/assessment` | 是 | 评估报告资源 |
| GET | `/api/resources` | 否 | 资源列表 |
| GET | `/api/resources/{id}` | 否 | 资源详情 |
| GET | `/api/resources/{id}/download` | 否 | 获取下载信息 |
| DELETE | `/api/resources/{id}` | 否 | 删除资源 |
| GET | `/api/resources/conversation/{talkId}` | 否 | 资源对话历史 |
| GET | `/api/resources/conversations` | 否 | 资源对话列表 |

通用生成请求：

```json
{
  "talkId": "456",
  "message": "生成脑梗死静脉溶栓复习资料",
  "resourceTypes": ["document"],
  "courseName": "神经病学",
  "knowledgePoints": ["静脉溶栓", "时间窗"],
  "difficulty": "intermediate",
  "images": []
}
```

单类型端点接收 `Map<String, Object>`，前端当前会传递课程、知识点、难度、诉求、画像和可选对话 ID。具体包装逻辑以 `ResourceController` 对应方法为准。

## 6. 学习路径

| 方法 | 路径 | SSE | 说明 |
|:---|:---|:---:|:---|
| POST | `/api/learning-path/generate` | 是 | 生成并持久化路径 |
| GET | `/api/learning-path` | 否 | 路径列表 |
| GET | `/api/learning-path/{pathId}` | 否 | 路径详情 |
| PUT | `/api/learning-path/{pathId}/steps/{stepId}/progress` | 否 | 更新步骤进度 |
| PUT | `/api/learning-path/tasks/{taskId}/progress` | 否 | 更新步骤内任务进度 |
| POST | `/api/learning-path/{pathId}/adjust` | 否 | 动态调整路径 |
| GET | `/api/learning-path/recommendations` | 否 | 查询推荐结果 |
| POST | `/api/learning-path/recommend` | 否 | 按请求生成推荐 |
| GET | `/api/learning-path/conversations` | 否 | 路径生成对话列表 |

生成请求：

```json
{
  "courseName": "神经病学",
  "goalDescription": "四周掌握急性缺血性脑卒中诊疗流程",
  "deadline": "2026-08-31",
  "weeklyHours": 6,
  "existingKnowledge": ["脑血管解剖"],
  "targetKnowledge": ["静脉溶栓", "血管内治疗"]
}
```

步骤进度请求字段：`status`、`actualHours`、`feedback`、`selfRating`。

## 7. 智能辅导

| 方法 | 路径 | SSE | 说明 |
|:---|:---|:---:|:---|
| POST | `/api/tutor/chat` | 是 | 完整辅导请求 |
| POST | `/api/tutor/ask` | 是 | 简化问答入口 |
| GET | `/api/tutor/conversation/{talkId}` | 否 | 辅导历史 |
| GET | `/api/tutor/conversations` | 否 | 辅导对话列表 |
| DELETE | `/api/tutor/conversation/{talkId}` | 否 | 删除辅导对话 |

```json
{
  "talkId": "789",
  "message": "为什么 DWI 对急性脑梗死更敏感？",
  "mode": "guided",
  "responseFormat": "markdown",
  "context": {
    "courseName": "神经病学",
    "knowledgePoints": ["MRI-DWI"],
    "relatedQuizId": null,
    "relatedCodePracticeId": null
  },
  "images": [],
  "codeSnippet": ""
}
```

## 8. 学习评估

| 方法 | 路径 | SSE | 说明 |
|:---|:---|:---:|:---|
| POST | `/api/evaluation/generate` | 是 | 生成评估报告 |
| GET | `/api/evaluation/report` | 否 | 获取单份/当前报告 |
| GET | `/api/evaluation/reports` | 否 | 报告列表 |
| GET | `/api/evaluation/reports/{id}` | 否 | 报告详情 |
| POST | `/api/evaluation/behavior` | 否 | 提交学习行为 |
| POST | `/api/evaluation/optimize` | 否 | 根据评估优化路径 |

评估请求：

```json
{
  "pathId": 12,
  "message": "评估最近阶段的学习情况",
  "assessmentType": "comprehensive",
  "timeRange": {
    "start": "2026-07-01",
    "end": "2026-07-29"
  },
  "courseName": "神经病学"
}
```

`assessmentType` 当前业务支持综合、知识、技能和进度等模式。前端雷达图固定展示知识掌握度、学习效率、技能应用、学习一致性、进度对齐度五个维度。

## 9. 代码辅助

| 方法 | 路径 | SSE | 说明 |
|:---|:---|:---:|:---|
| POST | `/api/code/execute` | 否 | 执行 Python 代码 |
| POST | `/api/code/assist` | 是 | AI 代码辅助 |

执行请求：

```json
{
  "code": "print('hello')",
  "language": "python",
  "timeout": 30,
  "inputData": ""
}
```

辅助请求：

```json
{
  "talkId": null,
  "assistType": "diagnose",
  "prompt": "定位报错并给出修复代码",
  "language": "python",
  "existingCode": "print(1 / 0)",
  "errorMessage": "ZeroDivisionError: division by zero"
}
```

`assistType` 必须为以下值之一：

| 值 | 功能 | 约束 |
|:---|:---|:---|
| `complete` | 代码补全 | 只补全缺失部分 |
| `diagnose` | 错误诊断 | 定位根因、修复并说明验证方式 |
| `optimize` | 优化建议 | 保持输出语义，优化性能、可读性或健壮性 |
| `explain` | 代码讲解 | 讲解结构和流程，不改写代码 |

后端会将选择值写入结构化提示，模型层不会再用模糊文本推断所选功能。`prompt` 和 `existingCode` 至少有一项非空。执行沙箱当前仅支持 Python。

## 10. 医学影像

| 方法 | 路径 | SSE | 说明 |
|:---|:---|:---:|:---|
| POST | `/api/medical/analyze-image` | 否 | 单次结构化影像分析 |
| POST | `/api/medical/analyze-case` | 是 | 多模态病例综合分析 |
| POST | `/api/medical/compare-images` | 否 | 多图比较 |
| POST | `/api/medical/dicom-metadata` | 否 | DICOM 元数据 |
| POST | `/api/medical/ocr/lab-report` | 否 | 检验报告 OCR |
| POST | `/api/medical/ocr/prescription` | 否 | 处方 OCR |
| POST | `/api/medical/dicom-to-png` | 否 | DICOM 预览转换 |

通用请求字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| `images` | string[] | Base64/Data URL 图片 |
| `question` | string | 分析问题 |
| `message` | string | 病例流式接口兼容字段 |
| `allInfo` | string | 可选画像或上下文 |
| `expectedImageType` | string | 可选期望影像类型 |
| `caseType` | string | `stroke`、`neuro` 或 `general` |
| `includeEvidence` | boolean | 是否检索本地循证资料 |
| `talkId` | string | 可选对话 ID |

## 11. 通用对话、课程和监控

| 方法 | 路径 | SSE | 说明 |
|:---|:---|:---:|:---|
| POST | `/api/user/ques/streamingQues` | 是 | 兼容通用流式问答 |
| GET | `/api/user/ques/getQues/{talk_id}` | 否 | 获取通用对话内容 |
| GET | `/api/courses` | 否 | 课程列表 |
| GET | `/api/courses/{courseId}/knowledge-tree` | 否 | 课程知识树 |
| GET | `/api/monitor/rate-limit/status` | 否 | 登录失败/成功计数和熔断状态 |
| GET | `/api/monitor/rate-limit/reset` | 否 | 清空登录限流相关 Redis 键 |

监控重置接口会修改系统状态，生产环境应增加管理员权限控制；当前代码只要求普通登录 Token。

## 12. Python 模型层内部接口

### 12.1 端点清单

| 方法 | 路径 | SSE | 调用方/用途 |
|:---|:---|:---:|:---|
| POST | `/model/get_result` | 是 | Java 后端统一多智能体推理入口，校验请求体 Token |
| GET | `/model/tasks/{task_id}` | 否 | 查询内存任务状态和结果 |
| GET | `/model/tasks/{task_id}/stream` | 是 | 按事件索引恢复任务流 |
| POST | `/model/profile/extract` | 否 | 从画像对话历史抽取 8 维画像 |
| POST | `/model/evaluation/optimize` | 否 | 生成路径优化 JSON |
| POST | `/model/code/execute` | 否 | Python 沙箱执行 |
| POST | `/model/code/assist` | 是 | 独立代码辅助路由 |
| POST | `/model/medical/analyze-image` | 否 | 结构化影像分析 |
| POST | `/model/medical/analyze-case` | 是 | 病例分析 |
| POST | `/model/medical/compare-images` | 否 | 多图对比 |
| POST | `/model/medical/dicom-metadata` | 否 | DICOM 元数据 |
| POST | `/model/medical/ocr/lab-report` | 否 | 检验报告 OCR |
| POST | `/model/medical/ocr/prescription` | 否 | 处方 OCR |
| POST | `/model/medical/ocr/text` | 是 | 通用医学文本 OCR，尚无 Java 代理端点 |
| POST | `/model/medical/dicom-to-png` | 否 | DICOM 转 PNG |
| POST | `/admin/reload_config` | 否 | 重载 YAML 配置 |
| GET | `/admin/report_modes` | 否 | 模型健康检查和报告模式列表 |

### 12.2 统一推理请求

```json
{
  "question": "业务层构造后的任务文本",
  "round": 2,
  "all_info": "历史摘要",
  "token": "backend-issued-internal-jwt",
  "report_mode": "tutor",
  "show_thinking": true,
  "images": []
}
```

模型专用路由中只有 `/model/get_result` 当前显式调用 `verify_token`。其他内部路由依赖 Docker/内网隔离，因此部署时不得将模型端口直接映射到公网。

## 13. 调用示例

### 13.1 登录

```bash
curl -X POST http://127.0.0.1:8080/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"name":"student01","password":"your-password"}'
```

### 13.2 代码辅助 SSE

```bash
curl -N -X POST http://127.0.0.1:8080/api/code/assist \
  -H "Content-Type: application/json" \
  -H "token: <jwt>" \
  -d '{"assistType":"complete","prompt":"补全函数","language":"python","existingCode":"def add(a, b):"}'
```

### 13.3 查看 Docker 模型健康状态

```bash
docker compose exec model curl -fsS http://127.0.0.1:8000/admin/report_modes
```

## 14. 维护说明

- 新增或删除控制器端点时，更新本页的总数与清单。
- 请求字段以 Java `param` 类和 Python Pydantic 模型为最终依据。
- SSE 客户端实现位于 `frontend/src/utils/sseStream.js`。
- 接口文档不再包含算法、数据库和测试报告正文；相关内容分别见 [核心算法设计文档](../architecture/核心算法设计文档.md)、[数据库设计手册](../architecture/数据库设计手册.md) 和 [系统测试报告](../architecture/系统测试报告.md)。
