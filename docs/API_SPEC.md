# MedLearn — 多智能体医学生个性化学习系统 接口文档

> **赛题场景**：在高等教育学习过程中，医学生普遍面临学习资源繁杂无序、难以精准匹配自身需求且缺乏智能化、个性化学习指导的核心问题。不同专业、不同学历水平的医学生，在面对海量课程资料、学术文献、临床辅助工具时，难以快速筛选出契合自身学习进度和能力的资源；同时课堂集体讲授模式无法兼顾每位学生的学习节奏与特点，导致学生在知识掌握和临床能力提升上存在明显差距。传统学习模式及基础的智能辅助系统，因缺乏多模态生成、多智能体协同、代码辅助开发等前沿AI技术的支撑，难以满足现代医学教育对培养创新型、个性化医学人才的要求。基于此，本系统以**神经病学**课程为切入点，构建多智能体协同的个性化学习智能体系统，融合多模态生成与代码辅助开发技术，依据学生个体情况提供定制化、多模态的学习内容，借助多智能体协作实现智能化、精准化的学习引导，真正实现"因材施教"的数字化落地。
>
> **系统定位**：基于现有 MedLLM / MultiAgentNeuroSystem 架构魔改，以**神经病学**课程为切入点，面向医学生构建多智能体个性化学习智能体系统。系统融合多模态生成技术（文档、思维导图、视频脚本、图解说明等）与代码辅助开发技术（医学数据分析编程、临床决策支持代码生成、医学AI模型实操等），通过多智能体协作实现个性化资源的自动化生成与建设，根据学生个体情况提供定制化、多模态的学习内容，全方位辅助医学生开展自主学习。
>
> **技术架构**：保留原有三层架构（Vue3 前端 → Java Spring Boot 后端 → Python FastAPI 模型层）、JWT 认证、SSE 流式推送、统一 Result 响应体、Hybrid RAG 检索等核心设计。新增代码辅助开发能力（代码生成、调试、运行沙箱）集成于模型层。
>
> **功能模块**：在原有脑卒中临床辅助决策能力基础上，新增五大核心模块——
> - **核心功能1**：对话式学习画像自主构建（必选）— 摒弃传统表单，通过自然语言对话自动抽取特征，构建≥6维度动态画像，支持随学随新
> - **核心功能2**：多智能体协同资源生成（必选）— 不同角色智能体协作生成≥5种个性化资源，融合多模态生成与代码辅助开发技术
> - **核心功能3**：个性化学习路径规划与资源推送（必选）— 规划科学动态的学习路径，基于画像精准推送多类型资源
> - **核心功能4**：智能辅导（可选加分项）— 提供文字解答、图解说明、短视频讲解等多模态答疑，含代码辅助辅导
> - **核心功能5**：学习效果评估（可选加分项）— 多维度精准评估，闭环动态调整学习路径与资源推送策略

---

## 1. 全局约定

### 1.1 Base URL

| 环境 | 后端 Base URL | 模型层 Base URL |
|------|--------------|----------------|
| 开发 | `http://localhost:8080/api` | `http://localhost:8000` |
| 生产 | `https://{domain}/api` | `https://{domain}/model` |

### 1.2 统一响应体 `Result`

所有非流式接口统一返回以下 JSON 结构（与原项目保持一致）：

```json
{
  "code": 1,
  "msg": "success",
  "data": {}
}
```

- `code`: 1=成功, 0=失败
- `msg`: 描述信息
- `data`: 业务数据，失败时可能为 null

### 1.3 认证方式

除 `/api/user/login` 和 `/api/user/register` 外，所有接口均需携带 JWT Token：

```
Authorization: Bearer <token>
token: <token>
```

后端通过 `Tokeninterceptor` + `ThreadLocalUtil` 解析用户身份，模型层通过 `verify_token()` 校验。

### 1.4 SSE 流式事件格式

流式接口（对话画像构建、资源生成、智能辅导、临床推理）采用 SSE（Server-Sent Events）协议，事件格式与原项目一致：

```
event: <事件类型>
id: <talkId>:<seq>
data: <JSON字符串>
```

**标准事件类型**：

| 事件类型 | 说明 | data 结构 |
|---------|------|----------|
| `init` | 连接建立，返回会话ID | `{"type":"init","talkId":"123","newTalk":true}` |
| `node_start` | 智能体节点开始推理 | `{"type":"node_start","node":"profiler","label":"正在分析学习特征..."}` |
| `chunk` | 内容片段（增量） | `{"type":"chunk","content":"..."}` |
| `thinking` | 思考过程展示 | `{"type":"thinking","step":1,"title":"知识基础分析","content":"..."}` |
| `result` | 一次性完整答案 | `{"type":"result","content":"..."}` |
| `done` | 流式结束 | `{"type":"done","talkId":"123","name":"学习画像构建"}` |
| `error` | 错误 | `{"type":"error","code":"E2001","message":"..."}` |
| `resume` | 断线续传恢复 | `{"type":"resume","talkId":"123","content":"..."}` |
| `warning` | 告警（超长截断等） | `{"type":"warning","message":"..."}` |

**心跳与关闭**：每 15 秒发送 `: heartbeat` comment，流结束后发送 `: close` comment。

**断线续传**：浏览器通过 `Last-Event-ID` 头携带最后收到的事件 ID（格式 `talkId:seq`），后端从缓存回放后续事件。

### 1.5 分页参数约定

所有分页接口统一使用以下查询参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 当前页码（从1开始） |
| `size` | int | 10 | 每页条数 |

分页响应结构：

```json
{
  "code": 1,
  "msg": "success",
  "data": {
    "total": 100,
    "records": [...]
  }
}
```

---

## 2. 用户认证模块

> 保留原项目用户体系，新增医学生专属字段（major、grade、specialty），用于画像初始化和学习资源匹配。

### 2.1 用户注册

**POST** `/api/user/register`

请求体：

```json
{
  "name": "string",
  "password": "string",
  "image": "string"
}
```

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": null
}
```

### 2.2 用户登录

**POST** `/api/user/login`

请求体：

```json
{
  "name": "string",
  "password": "string"
}
```

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": "eyJhbGciOiJIUzI1NiJ9..."
}
```

> `data` 为 JWT Token 字符串。

### 2.3 退出登录

**POST** `/api/user/logOut`

请求头：需携带 Token

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": null
}
```

### 2.4 获取用户信息

**GET** `/api/user/showInfo`

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": {
    "id": 1,
    "name": "李明",
    "image": "https://oss.example.com/avatar.jpg",
    "major": "临床医学",
    "grade": "大三",
    "specialty": "神经内科方向"
  }
}
```

> `major`、`grade`、`specialty` 为新增医学生专属字段，原 `User` 表需 ALTER 新增这三列。这些字段在首次登录后引导填写，作为画像初始化的种子信息。

### 2.5 修改用户信息

**PUT** `/api/user/showInfo/changeKey`

请求体：

```json
{
  "prePassword": "string",
  "newPassword": "string",
  "image": "string",
  "major": "string",
  "grade": "string",
  "specialty": "string"
}
```

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": null
}
```

### 2.6 文件上传

**POST** `/api/user/upload`

请求：`multipart/form-data`，字段名 `file`

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": "https://oss.example.com/uploads/xxx.pdf"
}
```

---

## 3. 对话式学习画像自主构建模块【核心功能1·必选】

> **赛题要求**：摒弃传统繁琐表单，支持通过自然语言对话（结合学生的专业、学习目标、学习历史等）自动抽取特征，构建包含不少于6个维度（如知识基础、认知风格、易错点偏好等）的动态学生画像，并支持画像的随学随新。
>
> **实现方式**：学生无需填写任何表单，只需与AI进行自然语言对话，系统自动从对话内容中抽取专业背景、学习阶段、知识水平、学习偏好等特征，实时构建并持续更新动态画像。
>
> **随学随新机制**：画像并非静态快照，而是随学生学习行为持续动态更新的活文档。系统在以下场景自动触发画像更新——
> - **对话触发**：学生与画像构建智能体对话时，实时抽取新特征并更新画像维度
> - **答题触发**：学生完成练习题后，根据答题结果自动更新知识基础、易错点等维度
> - **资源使用触发**：学生浏览/下载学习资源后，根据资源类型与时长更新资源偏好维度
> - **辅导触发**：智能辅导对话结束后，根据辅导内容更新认知风格、易错点等维度
> - **评估触发**：学习效果评估完成后，根据评估结果全面更新画像各维度
>
> 所有触发均由后端事件总线自动分发，学生无需主动操作即可实现画像的"随学随新"。

### 3.1 对话式画像构建（SSE 流式）

**POST** `/api/profile/conversation`

> Content-Type: `application/json`
> Response Content-Type: `text/event-stream`
>
> 摒弃传统表单，学生通过自然语言对话即可完成画像构建。系统自动从对话中抽取特征，无需手动填写。

请求体：

```json
{
  "talkId": "string|null",
  "message": "string",
  "images": ["string"]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| talkId | string | 否 | 对话ID，首次传 null 或不传，续聊传已有 talkId |
| message | string | 是 | 学生输入的自然语言内容 |
| images | string[] | 否 | 上传图片的 Base64 列表（如成绩单截图、笔记照片），最多3张 |

SSE 事件流示例：

```
event: init
data: {"type":"init","talkId":"1001","newTalk":true}

event: node_start
data: {"type":"node_start","node":"profiler","label":"正在分析学习特征..."}

event: thinking
data: {"type":"thinking","step":1,"title":"特征抽取","content":"正在从对话中自动抽取专业、学习阶段、知识水平等特征..."}

event: chunk
data: {"type":"chunk","content":"根据你的描述，"}

event: chunk
data: {"type":"chunk","content":"我为你构建了以下学习画像..."}

event: node_start
data: {"type":"node_start","node":"dimension_builder","label":"正在更新画像维度..."}

event: chunk
data: {"type":"chunk","content":"你的医学知识基础维度已更新为：已掌握神经解剖学基础..."}

event: done
data: {"type":"done","talkId":"1001","name":"学习画像构建"}
```

**多智能体协作说明**：

| 智能体角色 | 节点名 | 职责 |
|-----------|--------|------|
| 画像对话智能体 (Profiler Agent) | `profiler` | 与医学生自然对话，引导表达专业背景、学习阶段与需求，无需表单 |
| 特征抽取智能体 (Extractor Agent) | `extractor` | 从对话内容中自动抽取结构化特征（专业、方向、知识水平、临床经验等） |
| 画像构建智能体 (Portrait Builder Agent) | `dimension_builder` | 将抽取的特征映射到6+维度，生成/更新动态画像 |

### 3.2 获取当前学习画像

**GET** `/api/profile`

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": {
    "profileId": 1,
    "userId": 1,
    "dimensions": {
      "knowledgeBase": {
        "level": "intermediate",
        "description": "已掌握系统解剖学、生理学基础；对神经病学有初步了解，药理学薄弱",
        "masteredTopics": ["系统解剖学", "生理学", "病理学基础", "神经解剖学"],
        "weakTopics": ["药理学", "神经影像学", "临床诊断学"]
      },
      "cognitiveStyle": {
        "type": "visual_learner",
        "description": "视觉型学习者，偏好解剖图解和手术视频演示",
        "preferences": ["思维导图", "手术视频", "解剖图解", "病例动画"]
      },
      "learningGoal": {
        "shortTerm": "掌握神经内科常见病的诊断与治疗",
        "longTerm": "成为具备独立诊疗能力的神经内科医师",
        "currentCourse": "神经病学"
      },
      "errorPattern": {
        "description": "在药物配伍禁忌类题目中易出错，解剖定位题正确率较高",
        "frequentErrors": ["药物相互作用", "溶栓禁忌症", "鉴别诊断逻辑"],
        "errorType": "conceptual"
      },
      "learningPace": {
        "speed": "moderate",
        "description": "中等学习节奏，每周可投入15-20小时课外学习",
        "preferredDuration": "45min/session",
        "weeklyHours": 18
      },
      "resourcePreference": {
        "preferredTypes": ["video", "case_study", "mindmap", "clinical_guideline"],
        "description": "偏好手术视频和病例分析，较少阅读纯文字综述",
        "dislikedTypes": ["plain_text"]
      }
    },
    "rawConversationSummary": "该学生为临床医学专业大三学生，神经内科方向，已学完系统解剖学和生理学...",
    "updateTime": "2026-06-10 14:30:00",
    "createTime": "2026-06-08 09:00:00"
  }
}
```

**画像维度定义**（6个必选 + 2个扩展，满足赛题"不少于6个维度"要求）：

| 维度 | 字段名 | 说明 | 取值示例 |
|------|--------|------|---------|
| 知识基础 | `knowledgeBase` | 已掌握/薄弱知识点 | `level: beginner/intermediate/advanced` |
| 认知风格 | `cognitiveStyle` | 学习方式偏好 | `type: visual/auditory/kinesthetic/reading` |
| 学习目标与规划 | `learningGoal` | 短期/长期目标、当前课程 | 自由文本 |
| 易错点偏好 | `errorPattern` | 常犯错误类型与模式 | `errorType: conceptual/careful/procedural` |
| 学习节奏 | `learningPace` | 学习速度与时间投入 | `speed: slow/moderate/fast` |
| 资源偏好 | `resourcePreference` | 偏好的资源类型 | `preferredTypes: [video, case_study, ...]` |
| 临床实践经验 | `clinicalExperience` | （扩展）见习/实习经历与科室 | 科室列表 |
| 学习情绪状态 | `emotionState` | （扩展）当前学习压力与动力 | `motivation: high/medium/low` |

### 3.3 手动更新画像维度

**PUT** `/api/profile/dimensions`

> 除对话自动更新外，也支持手动微调画像维度。

请求体：

```json
{
  "knowledgeBase": {
    "level": "advanced",
    "description": "更新后的描述",
    "masteredTopics": ["系统解剖学", "生理学", "神经病学基础"],
    "weakTopics": ["药理学"]
  },
  "learningPace": {
    "speed": "fast",
    "weeklyHours": 25
  }
}
```

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": null
}
```

### 3.4 获取画像对话历史

**GET** `/api/profile/conversation/{talkId}`

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": [
    {
      "role": "user",
      "content": "我是临床医学大三学生，正在学神经病学，以后想走神经内科方向",
      "images": null,
      "timestamp": "2026-06-08 09:01:00"
    },
    {
      "role": "assistant",
      "content": "好的，我了解了你的专业背景。请问你目前对神经内科哪些疾病掌握得比较好？",
      "images": null,
      "timestamp": "2026-06-08 09:01:05"
    }
  ]
}
```

### 3.5 获取画像对话列表

**GET** `/api/profile/conversations`

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": [
    {
      "talkId": 1001,
      "title": "学习画像构建",
      "updateTime": "2026-06-10 14:30:00"
    },
    {
      "talkId": 1002,
      "title": "画像更新-期中考试后",
      "updateTime": "2026-06-09 10:00:00"
    }
  ]
}
```

### 3.6 删除画像对话

**DELETE** `/api/profile/conversation/{talkId}`

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": null
}
```

---

## 4. 多智能体协同资源生成模块【核心功能2·必选】

> **赛题要求**：系统须体现"多智能体"架构设计；通过与学生的智能交互，大模型结合AI前沿技术和工具，依据学生提供的专业、课程内容、知识短板、学习需求等信息，生成针对性的多模态学习资料，须由不同角色的智能体协作完成至少5种类型的个性化资源生成，如专业课程讲解文档、知识点思维导图、不同类型练习题目、拓展阅读材料、多模态教学视频/动画、代码类实操案例等，为学生提供全方位学习参考。
>
> **医学场景适配**：以神经病学课程为切入点，将"代码类实操案例"适配为"医学编程与数据分析实操"（医学数据分析编程、临床决策支持代码生成、医学AI模型实操等），同时保留"临床实操案例"作为独立的临床技能训练资源，并新增"实践项目学习材料"覆盖综合性实践项目。
>
> **资源类型（10种，满足赛题≥5种要求）**：
> 1. 医学课程讲解文档 — 对应赛题"专业课程讲解文档"
> 2. 医学知识体系思维导图 — 对应赛题"知识点思维导图"
> 3. 不同类型练习题目（含病例分析题） — 对应赛题"不同类型练习题目"
> 4. 临床指南与文献拓展阅读 — 对应赛题"拓展阅读材料"
> 5. 多模态教学视频/手术动画脚本 — 对应赛题"多模态教学视频/动画"
> 6. 医学编程与数据分析实操 — 对应赛题"代码类实操案例"，融合代码辅助开发技术
> 7. 临床实操案例/诊疗实操案例 — 医学特色资源，涵盖病史采集、体格检查、辅助检查判读、治疗方案制定等临床核心技能
> 8. 医学课程PPT — 对应赛题"PPT"
> 9. 资源设计方案 — 对应赛题"资源设计方案"
> 10. 实践项目学习材料 — 对应赛题"实践项目学习材料"，综合性实践项目（如：基于脑卒中数据构建预测模型、设计临床决策辅助工具等）

### 4.1 综合资源生成（SSE 流式）

**POST** `/api/resources/generate`

> 核心接口：根据医学生画像和学习需求，多智能体协同生成多种类型多模态医学学习资源。
> Content-Type: `application/json`
> Response Content-Type: `text/event-stream`

请求体：

```json
{
  "talkId": "string|null",
  "message": "帮我生成脑卒中相关的学习资料",
  "resourceTypes": [
    "document",
    "mindmap",
    "quiz",
    "reading",
    "video_script",
    "code_practice",
    "case_study",
    "ppt",
    "plan",
    "project"
  ],
  "courseName": "神经病学",
  "knowledgePoints": [
    "缺血性脑卒中",
    "静脉溶栓",
    "TOAST分型"
  ],
  "difficulty": "intermediate",
  "images": ["string"]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| talkId | string | 否 | 对话ID，首次为 null |
| message | string | 是 | 学习需求描述 |
| resourceTypes | string[] | 是 | 需要生成的资源类型，至少选1种 |
| courseName | string | 是 | 课程名称 |
| knowledgePoints | string[] | 否 | 知识点列表 |
| difficulty | string | 否 | 难度：beginner/intermediate/advanced |
| images | string[] | 否 | 参考图片 Base64 |

**resourceTypes 可选值**（10种，满足赛题≥5种要求）：

| 值 | 说明 | 对应赛题资源类型 |
|----|------|----------------|
| `document` | 医学课程讲解文档 | 专业课程讲解文档 |
| `mindmap` | 医学知识体系思维导图 | 知识点思维导图 |
| `quiz` | 医学练习题目（含病例分析题） | 不同类型练习题目 |
| `reading` | 临床指南与文献拓展阅读 | 拓展阅读材料 |
| `video_script` | 教学视频/手术动画脚本 | 多模态教学视频/动画 |
| `code_practice` | 医学编程与数据分析实操 | 代码类实操案例（融合代码辅助开发） |
| `case_study` | 临床实操案例/诊疗实操案例 | 实操案例（医学特色） |
| `ppt` | 医学课程PPT | PPT |
| `plan` | 资源设计方案 | 资源设计方案 |
| `project` | 实践项目学习材料 | 实践项目学习材料 |

SSE 事件流示例：

```
event: init
data: {"type":"init","talkId":"2001","newTalk":true}

event: node_start
data: {"type":"node_start","node":"requirement_analyzer","label":"正在分析学习需求..."}

event: thinking
data: {"type":"thinking","step":1,"title":"需求分析","content":"正在结合医学生画像分析资源需求..."}

event: node_start
data: {"type":"node_start","node":"document_writer","label":"正在生成课程讲解文档..."}

event: chunk
data: {"type":"chunk","content":"# 缺血性脑卒中诊疗详解\n\n## 1. 定义与流行病学\n..."}

event: node_start
data: {"type":"node_start","node":"mindmap_generator","label":"正在生成思维导图..."}

event: chunk
data: {"type":"chunk","content":"```mermaid\nmindmap\n  root((缺血性脑卒中))\n    TOAST分型\n      大动脉粥样硬化型\n      心源性栓塞型\n..."}

event: node_start
data: {"type":"node_start","node":"quiz_creator","label":"正在生成练习题目..."}

event: chunk
data: {"type":"chunk","content":"## 练习题\n\n### 病例分析题\n1. 男性，65岁，突发右侧肢体无力2小时...\n..."}

event: node_start
data: {"type":"node_start","node":"code_practice_agent","label":"正在生成医学编程实操案例..."}

event: chunk
data: {"type":"chunk","content":"## 医学编程实操：基于NIHSS评分的卒中严重度预测\n\n```python\nimport pandas as pd\nfrom sklearn.ensemble import RandomForestClassifier\n..."}

event: node_start
data: {"type":"node_start","node":"ppt_generator","label":"正在生成课程PPT..."}

event: chunk
data: {"type":"chunk","content":"# 脑卒中诊疗PPT\n\n## Slide 1: 概述\n..."}

event: node_start
data: {"type":"node_start","node":"project_designer","label":"正在生成实践项目学习材料..."}

event: chunk
data: {"type":"chunk","content":"# 实践项目：基于脑卒中数据的预测模型构建\n\n## 项目目标\n构建一个基于患者临床特征的缺血性脑卒中预后预测模型...\n..."}

event: done
data: {"type":"done","talkId":"2001","name":"资源生成完成"}
```

**多智能体协作矩阵**（10个专业智能体 + 1个质量审核智能体 + 1个代码沙箱服务）：

| 智能体角色 | 节点名 | 职责 | 生成资源类型 |
|-----------|--------|------|------------|
| 需求分析智能体 (Requirement Analyzer) | `requirement_analyzer` | 结合画像分析需求，拆解生成任务，调度各专业智能体 | — |
| 文档撰写智能体 (Document Writer) | `document_writer` | 生成医学课程讲解文档 | `document` |
| 思维导图智能体 (Mindmap Generator) | `mindmap_generator` | 生成医学知识体系思维导图（Mermaid/JSON） | `mindmap` |
| 题目生成智能体 (Quiz Creator) | `quiz_creator` | 生成不同类型医学练习题 | `quiz` |
| 文献推荐智能体 (Reading Curator) | `reading_curator` | 生成临床指南与文献拓展阅读推荐 | `reading` |
| 视频脚本智能体 (Video Script Writer) | `video_script_writer` | 生成多模态教学视频/手术动画脚本 | `video_script` |
| 代码实操智能体 (Code Practice Agent) | `code_practice_agent` | 生成医学编程与数据分析实操案例（Python/R代码），调用代码沙箱验证可运行性 | `code_practice` |
| 实操案例智能体 (Case Study Agent) | `case_study` | 生成临床实操案例/诊疗实操案例 | `case_study` |
| PPT生成智能体 (PPT Generator) | `ppt_generator` | 生成医学课程PPT（Markdown/JSON结构） | `ppt` |
| 方案设计智能体 (Plan Designer) | `plan_designer` | 生成资源设计方案（学习资源规划与组织方案） | `plan` |
| 实践项目智能体 (Project Designer) | `project_designer` | 生成实践项目学习材料（含项目目标、数据集、代码框架、评估标准） | `project` |
| 质量审核智能体 (Quality Reviewer) | `quality_reviewer` | 审核资源质量、医学准确性与个性化匹配度 | — |
| 代码沙箱服务 (Code Sandbox) | `code_sandbox` | 安全执行代码实操与实践项目中的代码片段，返回运行结果 | `code_practice`, `project` |

### 4.2 单类型资源生成（SSE 流式）

> 当只需要生成某一种类型的资源时，可使用单类型接口，减少推理开销。

#### 4.2.1 生成医学课程讲解文档

**POST** `/api/resources/generate/document`

请求体：

```json
{
  "courseName": "神经病学",
  "knowledgePoints": ["缺血性脑卒中", "静脉溶栓"],
  "difficulty": "intermediate",
  "style": "detailed",
  "profileAware": true
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| courseName | string | 是 | 课程名称 |
| knowledgePoints | string[] | 是 | 知识点列表 |
| difficulty | string | 否 | 难度级别 |
| style | string | 否 | 风格：detailed/concise/annotated |
| profileAware | boolean | 否 | 是否结合学生画像个性化，默认 true |

SSE 事件流：同 4.1 格式，仅 `document_writer` 节点工作。

#### 4.2.2 生成医学知识体系思维导图

**POST** `/api/resources/generate/mindmap`

请求体：

```json
{
  "courseName": "神经病学",
  "knowledgePoints": ["缺血性脑卒中", "TOAST分型"],
  "format": "mermaid",
  "depth": 3
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| courseName | string | 是 | 课程名称 |
| knowledgePoints | string[] | 是 | 知识点列表 |
| format | string | 否 | 输出格式：mermaid/json/svg，默认 mermaid |
| depth | int | 否 | 展开层级，默认 3 |

#### 4.2.3 生成不同类型练习题目

**POST** `/api/resources/generate/quiz`

请求体：

```json
{
  "courseName": "神经病学",
  "knowledgePoints": ["缺血性脑卒中"],
  "difficulty": "intermediate",
  "quizTypes": [
    "choice",
    "case_analysis",
    "short_answer",
    "true_false",
    "differential_diagnosis"
  ],
  "count": 10,
  "includeAnswer": true
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| courseName | string | 是 | 课程名称 |
| knowledgePoints | string[] | 是 | 知识点列表 |
| difficulty | string | 否 | 难度级别 |
| quizTypes | string[] | 否 | 题目类型（见下表） |
| count | int | 否 | 题目数量，默认 10 |
| includeAnswer | boolean | 否 | 是否包含参考答案，默认 true |

**quizTypes 可选值**（不同类型练习题目）：

| 值 | 说明 |
|----|------|
| `choice` | 单选题（A2/A3/A4型题） |
| `case_analysis` | 病例分析题 |
| `short_answer` | 简答题 |
| `true_false` | 判断题 |
| `differential_diagnosis` | 鉴别诊断题 |

#### 4.2.4 生成临床指南与文献拓展阅读

**POST** `/api/resources/generate/reading`

请求体：

```json
{
  "courseName": "神经病学",
  "knowledgePoints": ["缺血性脑卒中"],
  "readingType": "guideline",
  "language": "zh",
  "count": 5
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| courseName | string | 是 | 课程名称 |
| knowledgePoints | string[] | 是 | 知识点列表 |
| readingType | string | 否 | 类型：guideline/paper/book_chapter/tutorial |
| language | string | 否 | 语言：zh/en，默认 zh |
| count | int | 否 | 推荐数量，默认 5 |

#### 4.2.5 生成多模态教学视频/手术动画脚本

**POST** `/api/resources/generate/video-script`

> 融合多模态生成技术，生成包含画面描述、旁白脚本、动画指示的完整视频/动画脚本。

请求体：

```json
{
  "courseName": "神经病学",
  "knowledgePoints": ["静脉溶栓流程"],
  "duration": "5min",
  "style": "animation",
  "includeNarration": true,
  "includeVisual": true
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| courseName | string | 是 | 课程名称 |
| knowledgePoints | string[] | 是 | 知识点列表 |
| duration | string | 否 | 预期时长，如 "5min" |
| style | string | 否 | 风格：animation/lecture/interactive/surgery_demo |
| includeNarration | boolean | 否 | 是否包含旁白脚本，默认 true |
| includeVisual | boolean | 否 | 是否包含画面描述，默认 true |

#### 4.2.6 生成医学编程与数据分析实操

**POST** `/api/resources/generate/code-practice`

> 对应赛题"代码类实操案例"，融合代码辅助开发技术。生成包含完整代码、数据集说明、运行步骤的医学编程实操案例，涵盖医学数据分析、临床决策支持代码、医学AI模型训练等场景。代码经代码沙箱验证可运行性。

请求体：

```json
{
  "courseName": "神经病学",
  "knowledgePoints": ["缺血性脑卒中预后预测"],
  "codeType": "data_analysis",
  "language": "python",
  "difficulty": "intermediate",
  "includeDataset": true,
  "includeExplanation": true,
  "runInSandbox": true
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| courseName | string | 是 | 课程名称 |
| knowledgePoints | string[] | 是 | 知识点列表 |
| codeType | string | 否 | 代码类型：data_analysis/model_training/clinical_decision_support/medical_imaging/visualization |
| language | string | 否 | 编程语言：python/r，默认 python |
| difficulty | string | 否 | 难度级别 |
| includeDataset | boolean | 否 | 是否包含模拟数据集，默认 true |
| includeExplanation | boolean | 否 | 是否包含代码逐行解释，默认 true |
| runInSandbox | boolean | 否 | 是否在代码沙箱中验证运行，默认 true |

**codeType 可选值**：

| 值 | 说明 | 示例 |
|----|------|------|
| `data_analysis` | 医学数据分析 | 基于NIHSS评分的卒中严重度统计分析 |
| `model_training` | 医学AI模型训练 | 缺血性脑卒中预后预测模型构建 |
| `clinical_decision_support` | 临床决策支持代码 | 基于指南的溶栓适应症自动判别程序 |
| `medical_imaging` | 医学影像处理 | CT影像脑出血区域分割代码 |
| `visualization` | 医学数据可视化 | 脑卒中发病率地理热力图生成 |

#### 4.2.7 生成临床实操案例/诊疗实操案例

**POST** `/api/resources/generate/case-study`

> 医学特色资源，涵盖病史采集、体格检查、辅助检查判读、治疗方案制定等临床核心技能。与"医学编程与数据分析实操"（4.2.6）互补，本接口侧重临床诊疗思维与操作流程。

请求体：

```json
{
  "courseName": "神经病学",
  "knowledgePoints": ["缺血性脑卒中"],
  "caseType": "emergency",
  "difficulty": "intermediate",
  "includeDiagnosis": true,
  "includeTreatment": true,
  "includeFollowUp": false
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| courseName | string | 是 | 课程名称 |
| knowledgePoints | string[] | 是 | 知识点列表 |
| caseType | string | 否 | 病例类型：emergency/outpatient/inpatient/chronic |
| difficulty | string | 否 | 难度级别 |
| includeDiagnosis | boolean | 否 | 是否包含诊断过程，默认 true |
| includeTreatment | boolean | 否 | 是否包含治疗方案，默认 true |
| includeFollowUp | boolean | 否 | 是否包含随访计划，默认 false |

#### 4.2.8 生成医学课程PPT

**POST** `/api/resources/generate/ppt`

> 生成结构化课程PPT，输出为 Markdown/JSON 结构，前端可渲染为幻灯片或导出为 PPTX。

请求体：

```json
{
  "courseName": "神经病学",
  "knowledgePoints": ["缺血性脑卒中", "TOAST分型"],
  "slideCount": 15,
  "style": "academic",
  "includeSpeakerNotes": true
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| courseName | string | 是 | 课程名称 |
| knowledgePoints | string[] | 是 | 知识点列表 |
| slideCount | int | 否 | 幻灯片页数，默认 15 |
| style | string | 否 | 风格：academic/clinical/lecture |
| includeSpeakerNotes | boolean | 否 | 是否包含演讲者备注，默认 true |

#### 4.2.9 生成资源设计方案

**POST** `/api/resources/generate/plan`

> 生成学习资源规划与组织方案，为学生的某一课程/知识点规划应学习哪些资源、以何种顺序学习。

请求体：

```json
{
  "courseName": "神经病学",
  "knowledgePoints": ["缺血性脑卒中"],
  "goal": "系统掌握缺血性脑卒中的诊断与治疗",
  "availableTime": "2周"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| courseName | string | 是 | 课程名称 |
| knowledgePoints | string[] | 是 | 知识点列表 |
| goal | string | 否 | 学习目标 |
| availableTime | string | 否 | 可用学习时间 |

#### 4.2.10 生成实践项目学习材料

**POST** `/api/resources/generate/project`

> 对应赛题"实践项目学习材料"，生成综合性实践项目的完整学习材料，包含项目目标、背景知识、数据集说明、代码框架、分步实施指南、评估标准等。项目通常跨越多个知识点，需要学生综合运用所学完成。

请求体：

```json
{
  "courseName": "神经病学",
  "projectTitle": "基于脑卒中数据的预测模型构建",
  "knowledgePoints": ["缺血性脑卒中", "预后预测", "机器学习"],
  "projectType": "data_science",
  "difficulty": "advanced",
  "estimatedDuration": "2周",
  "includeCodeFramework": true,
  "includeDataset": true,
  "includeRubric": true
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| courseName | string | 是 | 课程名称 |
| projectTitle | string | 是 | 项目标题 |
| knowledgePoints | string[] | 是 | 涉及的知识点列表 |
| projectType | string | 否 | 项目类型：data_science/clinical_research/tool_development/case_series |
| difficulty | string | 否 | 难度级别 |
| estimatedDuration | string | 否 | 预计完成时长 |
| includeCodeFramework | boolean | 否 | 是否包含代码框架（脚手架代码），默认 true |
| includeDataset | boolean | 否 | 是否包含模拟数据集，默认 true |
| includeRubric | boolean | 否 | 是否包含评估标准（Rubric），默认 true |

**projectType 可选值**：

| 值 | 说明 | 示例 |
|----|------|------|
| `data_science` | 数据科学项目 | 基于脑卒中数据构建预后预测模型 |
| `clinical_research` | 临床研究项目 | 设计一项脑卒中溶栓疗效观察研究方案 |
| `tool_development` | 工具开发项目 | 开发一个简易NIHSS评分计算与记录工具 |
| `case_series` | 病例系列分析 | 收集并分析10例脑卒中患者的诊疗路径 |

### 4.3 获取资源列表

**GET** `/api/resources`

查询参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| page | int | 否 | 页码，默认1 |
| size | int | 否 | 每页条数，默认10 |
| type | string | 否 | 资源类型筛选：document/mindmap/quiz/reading/video_script/code_practice/case_study/ppt/plan/project |
| courseName | string | 否 | 课程名称筛选 |
| difficulty | string | 否 | 难度筛选 |

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": {
    "total": 25,
    "records": [
      {
        "resourceId": 301,
        "title": "缺血性脑卒中诊疗详解",
        "type": "document",
        "courseName": "神经病学",
        "difficulty": "intermediate",
        "knowledgePoints": ["缺血性脑卒中", "静脉溶栓"],
        "fileUrl": "https://oss.example.com/resources/301.docx",
        "createTime": "2026-06-10 14:30:00"
      }
    ]
  }
}
```

### 4.4 获取资源详情

**GET** `/api/resources/{id}`

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": {
    "resourceId": 301,
    "title": "缺血性脑卒中诊疗详解",
    "type": "document",
    "courseName": "神经病学",
    "difficulty": "intermediate",
    "knowledgePoints": ["缺血性脑卒中", "静脉溶栓"],
    "content": "# 缺血性脑卒中诊疗详解\n\n## 1. 定义与流行病学\n...",
    "fileUrl": "https://oss.example.com/resources/301.docx",
    "metadata": {
      "wordCount": 3500,
      "estimatedReadTime": "15min",
      "agentChain": ["requirement_analyzer", "document_writer", "quality_reviewer"]
    },
    "createTime": "2026-06-10 14:30:00",
    "updateTime": "2026-06-10 14:30:00"
  }
}
```

### 4.5 下载资源文件

**GET** `/api/resources/{id}/download`

响应：返回签名 URL

```json
{
  "code": 1,
  "msg": "success",
  "data": {
    "resourceId": 301,
    "previewUrl": "https://oss.example.com/signed/preview/...",
    "downloadUrl": "https://oss.example.com/signed/download/..."
  }
}
```

### 4.6 删除资源

**DELETE** `/api/resources/{id}`

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": null
}
```

### 4.7 资源对话历史

**GET** `/api/resources/conversation/{talkId}`

响应：同 3.4 格式。

### 4.8 资源对话列表

**GET** `/api/resources/conversations`

响应：同 3.5 格式。

---

## 5. 个性化学习路径规划与资源推送模块【核心功能3·必选】

> **赛题要求**：依托多智能体协同工作机制，整合系统生成的个性化资源，结合大模型对学生专业、学习进度、知识掌握情况及学习偏好的深度分析，为学生规划科学、动态的个性化学习路径，明确学习步骤和顺序；同时基于画像实现学习资源的精准推送，涵盖文档、视频、题库、实操案例等多类型内容。
>
> **实现方式**：路径规划与资源推送一体化设计——路径规划智能体根据画像生成阶段性学习路径，资源匹配智能体为每个路径节点精准推送匹配的学习资源（文档、视频、题库、实操案例等），难度调节智能体根据学习反馈动态调整路径难度与资源推荐策略。

### 5.1 生成学习路径（SSE 流式）

**POST** `/api/learning-path/generate`

> Content-Type: `application/json`
> Response Content-Type: `text/event-stream`

请求体：

```json
{
  "goal": "掌握神经内科常见病的诊断与治疗",
  "currentCourse": "神经病学",
  "targetExam": "神经病学期末考试",
  "deadline": "2026-07-15",
  "weeklyHours": 18
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| goal | string | 是 | 学习目标描述 |
| currentCourse | string | 否 | 当前课程名称 |
| targetExam | string | 否 | 目标考试/考核 |
| deadline | string | 否 | 截止日期，格式 yyyy-MM-dd |
| weeklyHours | int | 否 | 每周可投入学时 |

SSE 事件流示例：

```
event: init
data: {"type":"init","talkId":"3001","newTalk":true}

event: node_start
data: {"type":"node_start","node":"path_planner","label":"正在分析画像并规划学习路径..."}

event: thinking
data: {"type":"thinking","step":1,"title":"画像匹配","content":"正在结合你的学习画像分析最优学习路径..."}

event: chunk
data: {"type":"chunk","content":"# 个性化学习路径\n\n## 阶段一：基础巩固（2周）\n..."}

event: node_start
data: {"type":"node_start","node":"resource_matcher","label":"正在为路径节点匹配精准资源..."}

event: chunk
data: {"type":"chunk","content":"### 推荐资源\n- 📄 缺血性脑卒中诊疗详解\n- 🧠 脑卒中知识体系思维导图\n- 🎬 静脉溶栓流程动画\n..."}

event: done
data: {"type":"done","talkId":"3001","name":"学习路径规划"}
```

**多智能体协作说明**：

| 智能体角色 | 节点名 | 职责 |
|-----------|--------|------|
| 路径规划智能体 (Path Planner) | `path_planner` | 结合画像与目标，规划分阶段学习路径，明确学习步骤和顺序 |
| 资源匹配智能体 (Resource Matcher) | `resource_matcher` | 为路径节点精准推送匹配的医学学习资源（文档、视频、题库、实操案例等） |
| 难度调节智能体 (Difficulty Adjuster) | `difficulty_adjuster` | 根据画像与学习反馈动态调整各阶段难度与资源推荐策略 |

### 5.2 获取当前学习路径

**GET** `/api/learning-path`

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": {
    "pathId": 1,
    "userId": 1,
    "goal": "掌握神经内科常见病的诊断与治疗",
    "currentPhase": 1,
    "totalPhases": 4,
    "phases": [
      {
        "phaseId": 1,
        "title": "基础巩固",
        "description": "巩固神经解剖学和生理学基础，为临床学习打基础",
        "duration": "2周",
        "status": "in_progress",
        "tasks": [
          {
            "taskId": 101,
            "title": "复习脑的血液供应解剖",
            "type": "reading",
            "estimatedTime": "2小时",
            "status": "completed",
            "resourceId": 301,
            "pushedResources": [
              {
                "resourceId": 301,
                "title": "缺血性脑卒中诊疗详解",
                "type": "document",
                "matchReason": "匹配你的知识基础：神经解剖学"
              },
              {
                "resourceId": 305,
                "title": "脑血液供应解剖动画",
                "type": "video_script",
                "matchReason": "匹配你的认知风格：视觉型学习者"
              }
            ]
          },
          {
            "taskId": 102,
            "title": "完成脑卒中分类练习题",
            "type": "quiz",
            "estimatedTime": "1小时",
            "status": "pending",
            "resourceId": 303,
            "pushedResources": [
              {
                "resourceId": 303,
                "title": "脑卒中分类练习题",
                "type": "quiz",
                "matchReason": "针对你的易错点：鉴别诊断逻辑"
              }
            ]
          }
        ]
      },
      {
        "phaseId": 2,
        "title": "临床思维训练",
        "description": "通过病例分析培养临床推理能力",
        "duration": "3周",
        "status": "locked",
        "tasks": []
      }
    ],
    "createTime": "2026-06-08 09:00:00",
    "updateTime": "2026-06-10 14:30:00"
  }
}
```

### 5.3 更新学习进度

**PUT** `/api/learning-path/tasks/{taskId}/progress`

> 更新学习进度后，系统自动根据反馈动态调整后续路径与资源推送策略。

请求体：

```json
{
  "status": "completed",
  "feedback": "已掌握脑的血液供应解剖，但Willis环部分还需加强"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| status | string | 是 | 状态：pending/in_progress/completed/skipped |
| feedback | string | 否 | 学习反馈，用于动态调整后续路径与资源推送 |

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": {
    "pathAdjusted": true,
    "adjustmentNote": "根据反馈，已加强Willis环相关资源推荐",
    "newPushedResources": [
      {
        "resourceId": 310,
        "title": "Willis环变异与临床意义",
        "type": "document",
        "matchReason": "根据学习反馈精准推送：Willis环薄弱点补强"
      }
    ]
  }
}
```

### 5.4 获取个性化资源推送

**GET** `/api/learning-path/recommendations`

> 基于学生画像实现学习资源的精准推送，涵盖文档、视频、题库、实操案例等多类型内容。
> 系统根据画像维度（知识基础、认知风格、易错点、资源偏好等）综合计算推荐。

查询参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| courseName | string | 否 | 课程名称筛选 |
| type | string | 否 | 资源类型筛选：document/video_script/quiz/case_study/code_practice/project/mindmap/reading/ppt |
| count | int | 否 | 推荐数量，默认10 |

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": {
    "recommendations": [
      {
        "resourceId": 301,
        "title": "缺血性脑卒中诊疗详解",
        "type": "document",
        "courseName": "神经病学",
        "difficulty": "intermediate",
        "matchScore": 0.92,
        "matchReason": "匹配你的知识基础（药理学薄弱）和认知风格（视觉型）",
        "knowledgePoints": ["缺血性脑卒中", "静脉溶栓"]
      },
      {
        "resourceId": 305,
        "title": "静脉溶栓流程手术动画",
        "type": "video_script",
        "courseName": "神经病学",
        "difficulty": "intermediate",
        "matchScore": 0.88,
        "matchReason": "匹配你的资源偏好（视频）和易错点（溶栓禁忌症）",
        "knowledgePoints": ["静脉溶栓"]
      },
      {
        "resourceId": 303,
        "title": "脑卒中鉴别诊断练习题",
        "type": "quiz",
        "courseName": "神经病学",
        "difficulty": "intermediate",
        "matchScore": 0.85,
        "matchReason": "针对你的易错点（鉴别诊断逻辑）精准推送",
        "knowledgePoints": ["鉴别诊断", "TOAST分型"]
      },
      {
        "resourceId": 308,
        "title": "急性脑卒中急诊处理实操案例",
        "type": "case_study",
        "courseName": "神经病学",
        "difficulty": "advanced",
        "matchScore": 0.80,
        "matchReason": "匹配你的学习目标（掌握神经内科诊疗）",
        "knowledgePoints": ["急性脑卒中", "急诊处理"]
      }
    ],
    "basedOnProfile": {
      "knowledgeBase": "intermediate",
      "cognitiveStyle": "visual_learner",
      "weakTopics": ["药理学", "鉴别诊断"],
      "preferredTypes": ["video", "case_study", "mindmap"]
    }
  }
}
```

### 5.5 获取学习路径对话列表

**GET** `/api/learning-path/conversations`

响应：同 3.5 格式。

---

## 6. 智能辅导模块【核心功能4·可选加分项】

> **赛题要求**：当学生在学习过程中遇到问题时，系统提供即时、多模态的答疑解惑服务，通过智能体的数据分析、大模型的知识支持，结合多模态生成技术，为学生提供详细的文字解答、图解说明、短视频讲解等多样化解答形式，实现针对性学习引导。
>
> **实现方式**：辅导策略智能体根据画像选择辅导模式（苏格拉底式引导/直接解答/提示等），知识辅导智能体生成个性化讲解内容，多模态生成智能体将文字解答转化为图解说明或短视频脚本，代码辅导智能体提供医学编程与数据分析的代码辅助开发服务，实现多模态+代码辅助的综合答疑。

### 6.1 智能辅导对话（SSE 流式）

**POST** `/api/tutor/chat`

> Content-Type: `application/json`
> Response Content-Type: `text/event-stream`
>
> 支持多模态答疑：文字解答、图解说明、短视频讲解脚本等多种解答形式。

请求体：

```json
{
  "talkId": "string|null",
  "message": "为什么rt-PA溶栓有时间窗限制？超过4.5小时还能用吗？",
  "mode": "socratic",
  "responseFormat": "multimodal",
  "context": {
    "courseName": "神经病学",
    "knowledgePoints": ["静脉溶栓", "rt-PA"],
    "relatedQuizId": null,
    "relatedCodePracticeId": null
  },
  "images": ["string"],
  "codeSnippet": null
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| talkId | string | 否 | 对话ID，首次为 null |
| message | string | 是 | 学生提问内容 |
| mode | string | 否 | 辅导模式（见下表），默认 socratic |
| responseFormat | string | 否 | 回复格式：text/multimodal，默认 multimodal |
| context | object | 否 | 上下文信息 |
| images | string[] | 否 | 上传图片 Base64，最多3张 |
| codeSnippet | string | 否 | 学生提交的代码片段（用于代码辅助辅导模式），需配合 mode=code_assist 使用 |

**辅导模式 mode 可选值**：

| 值 | 说明 |
|----|------|
| `socratic` | 苏格拉底式引导，通过追问启发学生自主思考 |
| `direct` | 直接解答，给出完整答案与解析 |
| `hint` | 提示模式，只给线索不直接给答案 |
| `clinical_reasoning` | 临床推理引导，模拟接诊思路逐步推进 |
| `error_analysis` | 错题解析，分析错误原因并针对性补强 |
| `code_assist` | 代码辅助辅导，帮助学生调试、优化医学编程代码，融合代码辅助开发技术 |

**回复格式 responseFormat**：

| 值 | 说明 |
|----|------|
| `text` | 纯文字解答 |
| `multimodal` | 多模态解答：文字解答 + 图解说明 + 短视频讲解脚本 |

SSE 事件流示例（multimodal 模式）：

```
event: init
data: {"type":"init","talkId":"4001","newTalk":true}

event: node_start
data: {"type":"node_start","node":"tutor_strategy","label":"正在分析问题并选择辅导策略..."}

event: thinking
data: {"type":"thinking","step":1,"title":"画像匹配","content":"该学生在药理学方面较薄弱，采用引导式讲解..."}

event: node_start
data: {"type":"node_start","node":"tutor","label":"正在生成文字解答..."}

event: chunk
data: {"type":"chunk","content":"这是一个很好的问题！让我们一步步来思考。\n\n首先，你知道rt-PA的作用机制是什么吗？"}

event: node_start
data: {"type":"node_start","node":"visual_explainer","label":"正在生成图解说明..."}

event: chunk
data: {"type":"chunk","content":"```mermaid\ngraph TD\n    A[缺血半暗带] -->|时间推移| B[核心梗死区扩大]\n..."}

event: node_start
data: {"type":"node_start","node":"video_tutor","label":"正在生成短视频讲解脚本..."}

event: chunk
data: {"type":"chunk","content":"## 短视频讲解：rt-PA时间窗\n\n**画面1**：显示脑缺血半暗带随时间变化的动画...\n**旁白**：当脑血管被血栓堵塞后..."}

event: done
data: {"type":"done","talkId":"4001","name":"智能辅导"}
```

SSE 事件流示例（code_assist 代码辅助辅导模式）：

```
event: init
data: {"type":"init","talkId":"4002","newTalk":true}

event: node_start
data: {"type":"node_start","node":"tutor_strategy","label":"正在分析代码问题..."}

event: node_start
data: {"type":"node_start","node":"code_tutor","label":"正在分析代码并生成辅导建议..."}

event: chunk
data: {"type":"chunk","content":"你的代码有几个问题需要修正：\n\n1. 第12行：`df['NIHSS']` 列名拼写错误，数据集中是 `nihss_score`\n2. 第18行：缺失值处理应使用中位数而非均值（NIHSS评分为有序分类数据）\n\n修正后的代码：\n```python\ndf['nihss_score'].fillna(df['nihss_score'].median(), inplace=True)\n```"}

event: node_start
data: {"type":"node_start","node":"code_sandbox","label":"正在沙箱中验证修正代码..."}

event: chunk
data: {"type":"chunk","content":"✅ 代码验证通过，运行结果：Accuracy=0.82, AUC=0.89"}

event: done
data: {"type":"done","talkId":"4002","name":"代码辅助辅导"}
```

**多智能体协作说明**：

| 智能体角色 | 节点名 | 职责 |
|-----------|--------|------|
| 辅导策略智能体 (Tutor Strategy) | `tutor_strategy` | 根据画像选择辅导策略（苏格拉底/直接/提示/代码辅助等） |
| 知识辅导智能体 (Knowledge Tutor) | `tutor` | 执行辅导对话，生成个性化文字解答 |
| 图解说明智能体 (Visual Explainer) | `visual_explainer` | 将文字解答转化为图解说明（Mermaid/图片描述） |
| 视频讲解智能体 (Video Tutor) | `video_tutor` | 生成短视频讲解脚本（画面+旁白） |
| 临床推理引导智能体 (Clinical Reasoning Tutor) | `clinical_tutor` | 临床推理模式下的接诊思路引导 |
| 代码辅导智能体 (Code Tutor) | `code_tutor` | 代码辅助辅导模式下的代码调试、优化、解释，调用代码沙箱验证 |

### 6.2 获取辅导对话历史

**GET** `/api/tutor/conversation/{talkId}`

响应：同 3.4 格式。

### 6.3 获取辅导对话列表

**GET** `/api/tutor/conversations`

响应：同 3.5 格式。

### 6.4 删除辅导对话

**DELETE** `/api/tutor/conversation/{talkId}`

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": null
}
```

---

## 7. 学习效果评估模块【核心功能5·可选加分项】

> **赛题要求**：通过实时跟踪学生的学习行为、练习测试情况、资源使用反馈等数据，依托大模型的数据分析能力实现对学生学习效果的多维度、精准评估；并根据评估结果及时动态调整学习资源推送策略和学习计划，实现学习方案的持续优化。
>
> **实现方式**：评估智能体实时采集学习行为数据（答题记录、资源使用时长、辅导对话频次等），通过大模型进行多维度分析生成评估报告，并自动触发学习路径调整和资源推送策略更新，形成"评估→调整→优化"的闭环。

### 7.1 生成学习评估报告（SSE 流式）

**POST** `/api/assessment/generate`

> Content-Type: `application/json`
> Response Content-Type: `text/event-stream`
>
> 评估完成后自动触发学习路径调整和资源推送策略更新。

请求体：

```json
{
  "assessmentType": "comprehensive",
  "timeRange": {
    "start": "2026-05-01",
    "end": "2026-06-10"
  },
  "courseName": "神经病学"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| assessmentType | string | 否 | 评估类型：comprehensive/quiz_only/clinical_only，默认 comprehensive |
| timeRange | object | 否 | 评估时间范围 |
| courseName | string | 否 | 课程名称筛选 |

SSE 事件流示例：

```
event: init
data: {"type":"init","talkId":"5001","newTalk":true}

event: node_start
data: {"type":"node_start","node":"assessor","label":"正在分析学习数据..."}

event: thinking
data: {"type":"thinking","step":1,"title":"数据采集","content":"正在采集答题记录、资源使用时长、辅导对话频次等数据..."}

event: chunk
data: {"type":"chunk","content":"# 学习效果评估报告\n\n## 综合评分：78/100\n\n### 知识掌握度\n..."}

event: node_start
data: {"type":"node_start","node":"adjuster","label":"正在根据评估结果调整学习计划..."}

event: chunk
data: {"type":"chunk","content":"## 动态调整建议\n\n1. 加强药理学药物相互作用章节学习\n2. 增加鉴别诊断题练习量\n..."}

event: done
data: {"type":"done","talkId":"5001","name":"学习评估报告"}
```

**多智能体协作说明**：

| 智能体角色 | 节点名 | 职责 |
|-----------|--------|------|
| 评估智能体 (Assessor) | `assessor` | 采集学习行为数据，进行多维度精准评估 |
| 调整智能体 (Adjuster) | `adjuster` | 根据评估结果动态调整学习路径与资源推送策略 |

### 7.2 获取评估报告列表

**GET** `/api/assessment/reports`

查询参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| page | int | 否 | 页码 |
| size | int | 否 | 每页条数 |
| courseName | string | 否 | 课程筛选 |

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": {
    "total": 5,
    "records": [
      {
        "reportId": 1,
        "title": "神经病学综合评估-6月",
        "assessmentType": "comprehensive",
        "score": 78,
        "courseName": "神经病学",
        "createTime": "2026-06-10 14:30:00"
      }
    ]
  }
}
```

### 7.3 获取评估报告详情

**GET** `/api/assessment/reports/{id}`

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": {
    "reportId": 1,
    "title": "神经病学综合评估-6月",
    "assessmentType": "comprehensive",
    "score": 78,
    "courseName": "神经病学",
    "dimensions": {
      "knowledgeMastery": {
        "score": 72,
        "level": "intermediate",
        "details": "神经解剖学掌握良好，药理学需加强"
      },
      "clinicalReasoning": {
        "score": 81,
        "level": "intermediate",
        "details": "病例分析能力中等，鉴别诊断逻辑需提升"
      },
      "learningEfficiency": {
        "score": 85,
        "level": "good",
        "details": "学习节奏稳定，资源利用率高"
      },
      "errorCorrection": {
        "score": 65,
        "level": "needs_improvement",
        "details": "同类错误重复率较高，建议加强错题回顾"
      }
    },
    "suggestions": [
      "重点复习药理学药物相互作用章节",
      "增加鉴别诊断题的练习量",
      "建立错题本，每周回顾高频错题"
    ],
    "adjustmentResult": {
      "pathAdjusted": true,
      "adjustmentNote": "已根据评估结果动态调整学习路径：增加药理学专项训练阶段",
      "resourcePushUpdated": true,
      "newPushedResources": [
        {
          "resourceId": 320,
          "title": "药物相互作用专项练习",
          "type": "quiz",
          "matchReason": "评估发现药理学薄弱，精准推送补强资源"
        }
      ]
    },
    "createTime": "2026-06-10 14:30:00"
  }
}
```

> 评估报告中的 `adjustmentResult` 字段体现了赛题要求的"根据评估结果及时动态调整学习资源推送策略和学习计划"闭环机制。

---

## 8. 代码辅助开发模块【赛题核心技术能力】

> **赛题要求**：系统需融合"代码辅助开发"技术，实现个性化资源的自动化生成与建设。
>
> **医学场景适配**：代码辅助开发在医学教育中体现为——医学数据分析编程辅助、临床决策支持代码生成、医学AI模型实操辅助、代码调试与运行验证等。本模块为资源生成模块（4.2.6代码实操、4.2.10实践项目）和智能辅导模块（6.1代码辅助辅导模式）提供底层代码能力支撑。

### 8.1 代码执行沙箱

**POST** `/api/code/execute`

> 在安全沙箱中执行学生或系统生成的代码，返回运行结果。供代码实操、实践项目、代码辅导等场景调用。

请求体：

```json
{
  "code": "import pandas as pd\ndf = pd.read_csv('/data/stroke_data.csv')\nprint(df.describe())",
  "language": "python",
  "timeout": 30,
  "inputData": {
    "/data/stroke_data.csv": "base64_encoded_csv_content"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | 待执行代码 |
| language | string | 否 | 编程语言：python/r，默认 python |
| timeout | int | 否 | 超时时间（秒），默认 30，最大 120 |
| inputData | object | 否 | 输入数据文件映射，key为文件路径，value为Base64编码内容 |

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": {
    "exitCode": 0,
    "stdout": "       age  nihss_score  ...\ncount  500.0       500.0  ...\n",
    "stderr": "",
    "outputFiles": {
      "/output/model.pkl": "base64_encoded_model_file"
    },
    "executionTime": 2.3
  }
}
```

### 8.2 代码辅助生成

**POST** `/api/code/assist`

> 根据自然语言描述生成医学编程代码片段，融合代码辅助开发技术。

请求体：

```json
{
  "prompt": "用Python实现一个基于NIHSS评分的卒中严重度分类函数",
  "language": "python",
  "context": {
    "courseName": "神经病学",
    "knowledgePoints": ["NIHSS评分", "卒中严重度"]
  },
  "existingCode": null
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| prompt | string | 是 | 代码需求描述 |
| language | string | 否 | 编程语言：python/r，默认 python |
| context | object | 否 | 医学上下文信息 |
| existingCode | string | 否 | 已有代码（用于续写/修改场景） |

响应：

```json
{
  "code": 1,
  "msg": "success",
  "data": {
    "generatedCode": "def classify_stroke_severity(nihss_score):\n    \"\"\"基于NIHSS评分的卒中严重度分类\n    0: 无卒中症状\n    1-4: 轻度卒中\n    5-15: 中度卒中\n    16-20: 中重度卒中\n    21-42: 重度卒中\n    \"\"\"\n    if nihss_score == 0:\n        return '无卒中症状'\n    elif nihss_score <= 4:\n        return '轻度卒中'\n    elif nihss_score <= 15:\n        return '中度卒中'\n    elif nihss_score <= 20:\n        return '中重度卒中'\n    else:\n        return '重度卒中'",
    "explanation": "该函数根据NIHSS评分标准将卒中严重度分为5个等级...",
    "sandboxVerified": true,
    "sandboxResult": {
      "exitCode": 0,
      "stdout": "中度卒中"
    }
  }
}
```

---

## 9. 赛题要求覆盖映射

> 本节清晰展示系统各功能模块与赛题要求的对应关系，确保赛题每一项要求均有明确的实现方案和接口支撑。

### 9.1 核心功能覆盖

| 赛题要求 | 系统模块 | 关键接口 | 覆盖说明 |
|---------|---------|---------|---------|
| **核心功能1：对话式学习画像自主构建** | 第3节 画像构建模块 | `POST /api/profile/conversation` | 摒弃表单，通过自然语言对话自动抽取特征；构建≥6维度动态画像（知识基础、认知风格、学习目标、易错点、学习节奏、资源偏好+临床经验、情绪状态）；支持随学随新（5种触发机制） |
| **核心功能2：多智能体协同资源生成** | 第4节 资源生成模块 | `POST /api/resources/generate` | 10个专业智能体+1个质量审核智能体+1个代码沙箱协作；10种资源类型（≥5种要求）；融合多模态生成与代码辅助开发技术 |
| **核心功能3：个性化学习路径规划与资源推送** | 第5节 学习路径模块 | `POST /api/learning-path/generate`、`GET /api/learning-path/recommendations` | 3个智能体协同规划动态学习路径；基于画像精准推送文档/视频/题库/实操案例等多类型资源 |
| **核心功能4：智能辅导（可选加分项）** | 第6节 智能辅导模块 | `POST /api/tutor/chat` | 6个智能体协同；6种辅导模式（含代码辅助辅导）；多模态答疑（文字+图解+短视频+代码验证） |
| **核心功能5：学习效果评估（可选加分项）** | 第7节 评估模块 | `POST /api/assessment/generate` | 2个智能体协同；多维度精准评估；闭环动态调整学习路径与资源推送策略 |

### 9.2 关键技术覆盖

| 赛题技术要求 | 系统实现 | 涉及模块 |
|-------------|---------|---------|
| **多模态生成** | 文档生成、思维导图（Mermaid/JSON）、视频脚本（画面+旁白）、图解说明、PPT、代码生成 | 第4节、第6节 |
| **多智能体协同** | 10+专业智能体+质量审核+代码沙箱，需求分析智能体统一调度 | 第3-7节 |
| **代码辅助开发** | 代码生成、代码调试、代码沙箱执行验证、代码辅助辅导 | 第4.2.6节、第4.2.10节、第6.1节、第8节 |

### 9.3 资源类型覆盖

| 赛题提及资源类型 | 系统资源类型 | 接口 |
|----------------|------------|------|
| 专业课程讲解文档 | 医学课程讲解文档 | `POST /api/resources/generate/document` |
| 知识点思维导图 | 医学知识体系思维导图 | `POST /api/resources/generate/mindmap` |
| 不同类型练习题目 | 不同类型练习题目（含病例分析题） | `POST /api/resources/generate/quiz` |
| 拓展阅读材料 | 临床指南与文献拓展阅读 | `POST /api/resources/generate/reading` |
| 多模态教学视频/动画 | 多模态教学视频/手术动画脚本 | `POST /api/resources/generate/video-script` |
| 代码类实操案例 | 医学编程与数据分析实操 | `POST /api/resources/generate/code-practice` |
| PPT | 医学课程PPT | `POST /api/resources/generate/ppt` |
| 资源设计方案 | 资源设计方案 | `POST /api/resources/generate/plan` |
| 实践项目学习材料 | 实践项目学习材料 | `POST /api/resources/generate/project` |
| （医学特色） | 临床实操案例/诊疗实操案例 | `POST /api/resources/generate/case-study` |

### 9.4 画像维度覆盖

| 赛题要求维度 | 系统画像维度 | 字段名 |
|-------------|------------|--------|
| 知识基础 | 知识基础 | `knowledgeBase` |
| 认知风格 | 认知风格 | `cognitiveStyle` |
| 易错点偏好 | 易错点偏好 | `errorPattern` |
| （赛题"等"字扩展） | 学习目标与规划 | `learningGoal` |
| （赛题"等"字扩展） | 学习节奏 | `learningPace` |
| （赛题"等"字扩展） | 资源偏好 | `resourcePreference` |
| （医学特色扩展） | 临床实践经验 | `clinicalExperience` |
| （医学特色扩展） | 学习情绪状态 | `emotionState` |

> 合计8个维度（6个必选+2个扩展），满足赛题"不少于6个维度"要求。