# LearnAgent 文档总览

> 状态：2026-07-30 按当前代码核对。代码、配置与数据库脚本是实现事实源；需求和竞赛文档用于描述目标与方案，不应覆盖代码事实。

## 阅读顺序

| 读者 | 建议入口 |
|:---|:---|
| 首次运行项目 | [根 README](../README.md) |
| 前后端联调 | [接口文档](api/LearnAgent系统接口文档.md) |
| 架构与维护 | [系统设计说明书](architecture/系统设计说明书.md) |
| 产品与验收 | [需求规格说明书](architecture/需求规格说明书.md) |
| 算法维护 | [核心算法设计文档](architecture/核心算法设计文档.md) |
| 数据库维护 | [数据库设计手册](architecture/数据库设计手册.md) |
| 测试与交付 | [系统测试报告](architecture/系统测试报告.md) |
| 参赛材料 | [中国软件杯说明](competition/中国软件杯.md) |

## 权威文档

| 文档 | 维护范围 | 主要事实源 |
|:---|:---|:---|
| [接口文档](api/LearnAgent系统接口文档.md) | Java 业务端点、Python 内部端点、请求字段、SSE 协议 | `backend/server/.../controller`、`param`、`model/app/routers` |
| [系统设计说明书](architecture/系统设计说明书.md) | 分层架构、运行时组件、数据流、安全边界、部署 | `docker-compose.yml`、三端入口与配置 |
| [需求规格说明书](architecture/需求规格说明书.md) | 功能和非功能需求、验收口径 | 当前页面、控制器和业务流程 |
| [核心算法设计文档](architecture/核心算法设计文档.md) | LangGraph、RAG、校验、画像、共享记忆 | `model/app/agents`、`model/app/rag` |
| [数据库设计手册](architecture/数据库设计手册.md) | 14 张表、索引与关系 | `backend/server/learningo_agents.sql` |
| [系统测试报告](architecture/系统测试报告.md) | 当前可复现测试结果和缺口 | `model/tests`、`frontend/tests`、`backend/server/src/test` |

## 专题文档

- [共享记忆系统](architecture/共享记忆系统.md)
- [医学影像识别与拦截系统](architecture/医学影像识别与拦截系统.md)

## 竞赛交付材料

- [中国软件杯技术说明](competition/中国软件杯.md)
- 竞赛报名表包含个人信息，仅在本地保管，不纳入 Git。
- [答辩演示稿（2026-06-19 快照）](competition/LearnAgent答辩稿-2026-06-19.pptx)
- [演示视频](competition/LearnAgent演示视频.mp4)

## 文件组织

- `docs/api/LearnAgent系统接口文档.md` 是唯一权威接口文档。
- `docs/competition/中国软件杯.md` 是唯一权威竞赛 Markdown 文档。
- `docs/architecture/` 只保存需求、设计、算法、数据库和测试文档，不存放竞赛交付文件。
- 竞赛 PPT 和视频是带日期的交付快照，不会随代码自动同步；使用前应根据本页权威 Markdown 复核。
- `~$LearnAgent.pptx` 是 Office 临时锁文件，不属于项目文档，不应提交。

## 更新规则

1. 接口变更时，同时更新接口文档和对应测试。
2. 依赖版本只引用清单文件，避免在多份文档中手工维护。
3. 测试报告只记录可复现命令与当次结果；历史压测必须标注环境、日期和原始结果文件。
4. 未实现功能必须标记为“规划”或“预留”，不得写入当前接口清单。
5. 文档中的本地链接必须使用仓库相对路径，不使用 `file:///` 绝对路径。
