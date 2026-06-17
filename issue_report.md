# Issue Report — 深度代码审查报告

**审查日期**: 2026-06-16  
**审查范围**: 全项目源码（Java Spring Boot 后端 + Python LangGraph 模型服务）  
**审查原则**: 拒绝补丁式修复 · 架构级思考 · 协同兼容保证

---

## 执行摘要

本次审查共发现并修复 **7 个问题**，覆盖：功能性 Bug（2）、安全漏洞（3）、数据一致性 Bug（1）、资源/性能 Bug（1）。所有修复均在保证向后兼容的前提下完成，无破坏性变更。

---

## 问题清单

### 🔴 P0 — 安全漏洞

---

#### ISSUE-001 · BCrypt 密码比对逻辑错误导致密码修改永远失败

| 字段 | 内容 |
|---|---|
| **文件** | `backend/.../service/impl/ChangeKeyServiceImpl.java` |
| **原始行** | 36 |
| **严重级别** | P0 · 安全 |

**根本原因**  
`user.getPassword().equals(changeKey.getPrePassword())` 将数据库中存储的 BCrypt 哈希值（`$2a$10$...`）与用户输入的明文直接做字符串比较，永远返回 `false`，导致用户合法密码也被判定为"密码错误"，无法修改密码。

**影响范围**  
所有已注册且密码经过 BCrypt 哈希处理的用户均无法通过密码验证。

**修复方案**  
使用 `BCryptPasswordEncoder.matches(rawPassword, encodedPassword)` 进行安全比对，同时对旧系统中存储的明文密码保留字符串回退路径（`startsWith("$2a$")` / `"$2b$"` 前缀判断），确保新旧数据均可正常比对。

---

#### ISSUE-002 · 新密码以明文存入数据库

| 字段 | 内容 |
|---|---|
| **文件** | `backend/.../service/impl/ChangeKeyServiceImpl.java` |
| **原始行** | 37 |
| **严重级别** | P0 · 安全 |

**根本原因**  
`user.setPassword(changeKey.getNewPassword())` 直接将用户输入的新密码明文写入 `user` 对象并持久化到数据库，完全绕过密码哈希机制。

**影响范围**  
所有使用修改密码功能的用户，新密码以明文形式持久化至数据库，一旦数据库泄露即等同于明文密码泄露。

**修复方案**  
改为 `user.setPassword(passwordEncoder.encode(changeKey.getNewPassword()))`，使用 Spring Security 注入的 `BCryptPasswordEncoder` 对新密码进行哈希。

---

#### ISSUE-003 · 密码明文写入 Redis（密码冷却 Key 值）

| 字段 | 内容 |
|---|---|
| **文件** | `backend/.../service/impl/ChangeKeyServiceImpl.java` |
| **原始行** | 60 |
| **严重级别** | P0 · 安全 |

**根本原因**  
`stringRedisTemplate.opsForValue().set("user:password:" + currentId, changeKey.getNewPassword(), 30, TimeUnit.DAYS)` 将用户新密码明文作为 Redis Value 存储，Key 前缀语义也从"冷却标记"变成了"密码缓存"，产生严重的信息泄露风险。

**影响范围**  
Redis 实例可访问者（包括获得 Redis 连接权限的攻击者）可直接读取所有近期修改过密码的用户的明文新密码。

**修复方案**  
1. Key 前缀改为 `user:pwd_changed:{userId}`，语义清晰只表示"已修改过密码的标记位"。  
2. Value 改为字面量 `"1"`，不存储任何凭据信息。  
3. 仅在本轮确实修改了密码时写入冷却标记。

---

### 🔴 P1 — 功能性 Bug（主流程失效）

---

#### ISSUE-004 · 资源生成/智能辅导/学习评估返回"学习者画像"内容

| 字段 | 内容 |
|---|---|
| **文件** | `ResourceController.java` · `TutorController.java` · `AssessmentController.java` |
| **严重级别** | P1 · 功能 |

**根本原因**  
三个 Controller 的 `buildSSEStream()` / 直接调用路径均使用了 5 参数重载 `streamChat(userId, talkId, question, token, images)`，该重载内部硬编码 `DEFAULT_REPORT_MODE = "emergency"`。Python 端 `ReportNode` 根据 `report_mode` 选择 YAML 模板，`emergency` 模板第一节为"## 一、学习者画像概览"，导致所有这三个模块的 AI 输出均返回用户画像内容而非预期功能内容。

**数据流路径**  
```
Controller.buildSSEStream()
  → streamChat(5-param)  // DEFAULT_REPORT_MODE = "emergency"
  → HTTP POST /model/get_result { report_mode: "emergency" }
  → Python ReportNode
  → YAML template: emergency → "学习者画像概览"
```

**影响范围**  
- `ResourceController` → `/api/resource/**` — 应返回学习资源，实际返回画像
- `TutorController` → `/api/tutor/**` — 应返回智能辅导，实际返回画像  
- `AssessmentController` → `/api/evaluation/generate` — 应返回评估报告，实际返回画像

**修复方案**  
为三处调用补充第 6 个参数 `reportMode`：
- `ResourceController`: `"resource_generate"`
- `TutorController`: `"tutor"`
- `AssessmentController`: `"assessment"`

`ProfileController` 已正确传递 `"profile_build"`，无需修改。

---

### 🟡 P2 — 数据一致性 Bug

---

#### ISSUE-005 · 对话持久化后 Redis 历史缓存未清除，导致下轮对话携带陈旧上下文

| 字段 | 内容 |
|---|---|
| **文件** | `backend/.../service/impl/ConversationPersistenceService.java` |
| **原始行** | 92（修复后） |
| **严重级别** | P2 · 数据一致性 |

**根本原因**  
`ConversationPersistenceService.persistConversation()` 将对话写入数据库后未清除对应的 Redis 历史缓存（Key: `chat:history:{userId}:{talkId}`）。`AIStreamingServiceImpl` 在下一轮对话发起时优先读取 Redis 缓存，而缓存中此时仍是上一轮的"旧历史"，新写入的记录在下一次 Redis 过期前不会被加载，导致模型收到的历史上下文不一致。

**修复方案**  
1. 在 `ConversationPersistenceService` 中注入 `StringRedisTemplate`。  
2. 在 `persistConversation()` 完成数据库写入后，执行 `stringRedisTemplate.delete("chat:history:" + userId + ":" + talkId)`，确保下一次请求从数据库重新加载最新记录。

---

### 🟡 P2 — 性能 Bug

---

#### ISSUE-006 · 画像提取函数双重调用 LLM（每次请求实际执行两次 LLM 推理）

| 字段 | 内容 |
|---|---|
| **文件** | `model/app/main.py` — `_extract_profile_from_conversation()` |
| **原始行** | 739–747 |
| **严重级别** | P2 · 性能 |

**根本原因**  
`_run_sync()` 在 `threading.Thread(target=_run_sync)` 中执行时，线程返回值被丢弃（`threading.Thread` 不捕获 `target` 函数的返回值）。线程 join 完成后，代码又在主线程直接调用 `result = _run_sync()`，触发第二次完整的 LLM 推理（网络请求 + Token 消耗），且第一次的结果被完全浪费。

**影响范围**  
每次触发画像提取时，实际向 DeepSeek API 发出两次请求，造成 2× Token 消耗和 2× 延迟。

**修复方案**  
引入 `result_container = [None]` 闭包容器，在 `_run_sync()` 内部将结果写入容器（`result_container[0] = dimensions`），线程结束后从容器读取结果，彻底消除重复调用。

---

### 🟡 P2 — 配置 Bug（启动崩溃风险）

---

#### ISSUE-007 · 环境变量名含连字符导致进程启动时崩溃

| 字段 | 内容 |
|---|---|
| **文件** | `model/app/utils/naming_model.py` |
| **原始行** | 16–18 |
| **严重级别** | P2 · 可用性 |

**根本原因**  
`os.environ.get("DEEPSEEK-API-KEY")` 使用了非标准的连字符变量名（大多数 Shell 不允许赋值含连字符的环境变量，如 `export DEEPSEEK-API-KEY=xxx` 在 bash/zsh 中会语法报错），导致实际读取结果永远为 `None`。随后 `raise ValueError(...)` 在 `NamingModel.__init__()` 中抛出，由于此类在模块导入时即被实例化，整个 Python 服务进程会在启动阶段即崩溃。

**修复方案**  
1. 变量名改为 `DEEPSEEK_API_KEY`（下划线），与 `.env` 文件约定和其他模块保持一致。  
2. 将 `raise ValueError` 改为 `logger.warning` + `self.llm = None`，延迟到实际调用 `run_naming()` 时才降级处理（返回默认标题 `"学习咨询"`），确保 API Key 缺失时服务进程仍可正常启动，其余功能不受影响。

---

## 修复统计

| ID | 文件 | 类型 | 严重级别 | 状态 |
|---|---|---|---|---|
| ISSUE-001 | `ChangeKeyServiceImpl.java` | 安全：BCrypt 比对错误 | P0 | ✅ 已修复 |
| ISSUE-002 | `ChangeKeyServiceImpl.java` | 安全：明文密码入库 | P0 | ✅ 已修复 |
| ISSUE-003 | `ChangeKeyServiceImpl.java` | 安全：明文密码写 Redis | P0 | ✅ 已修复 |
| ISSUE-004 | `ResourceController.java` / `TutorController.java` / `AssessmentController.java` | 功能：report_mode 路由错误 | P1 | ✅ 已修复 |
| ISSUE-005 | `ConversationPersistenceService.java` | 数据一致性：缓存未清除 | P2 | ✅ 已修复 |
| ISSUE-006 | `main.py` | 性能：LLM 双重调用 | P2 | ✅ 已修复 |
| ISSUE-007 | `naming_model.py` | 配置：环境变量名非法 | P2 | ✅ 已修复 |

---

## 未修改说明

以下模块经审查无需变动：

- `AIStreamingServiceImpl.java` — `DEFAULT_REPORT_MODE` 设计合理，仅作内部兜底；6 参数重载签名清晰，无需改动。
- `ProfileController.java` — 已正确传递 `"profile_build"`。
- `RefreshTokenInterceptor.java` / `Tokeninterceptor.java` — ThreadLocal 模式无缺陷，双拦截器 order 顺序正确。
- `SSEEventCache.java` — 环形缓冲 + TTL 设计合理，重连逻辑完整。
- `report_templates.yaml` — 各 mode 的模板内容与业务需求匹配，无需修改。

---

## 后续建议（不在本次修复范围内）

1. **密码迁移**: 数据库中仍可能存在历史明文密码记录。建议在下一次用户登录时强制触发一次 BCrypt 重新加密存储（在 `LoginServiceImpl` 中检测明文密码并即时升级哈希）。
2. **线程池统一管理**: `_extract_profile_from_conversation` 使用裸 `threading.Thread`，建议统一迁移至 `concurrent.futures.ThreadPoolExecutor` 以支持更好的超时控制和异常传播。
3. **`ConversationPersistenceService` 中 `List` import 清理**: 移除 `_extract_profile_from_conversation` 后 `List` import 可能变为未使用，建议 IDE 检查一轮。
