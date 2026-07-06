# LearnAgent Frontend

多智能体个性化学习系统前端项目

## 项目简介

基于 Vue 3 开发的个性化学习智能体系统前端应用。支持用户注册登录、对话式学习画像构建、个性化资源生成与预览、智能辅导问答、学习路径规划与进度追踪、学习效果评估等功能。采用 SSE 流式响应技术，实时展示 AI 推理思考过程。

## 技术栈

- **框架**: Vue 3.5 (Composition API)
- **构建工具**: Vite 7
- **状态管理**: Pinia 3 (支持持久化)
- **路由**: Vue Router 4
- **HTTP 客户端**: Axios
- **Markdown 渲染**: marked 17 + DOMPurify 3.3
- **PDF 预览**: pdfjs-dist 3.11 + vue-pdf-embed 2.1
- **样式**: Normalize.css + Sass
- **开发工具**: ESLint + Prettier

## 功能特性

- ✅ 用户注册与登录
- ✅ 用户信息管理（头像上传、密码修改）
- ✅ 对话式学习画像自主构建（SSE 流式）
- ✅ 多智能体协同资源生成与预览
- ✅ 智能辅导问答（支持多模态图片上传）
- ✅ 个性化学习路径规划与进度追踪
- ✅ 学习效果评估与热力图展示
- ✅ AI 思考过程实时流式渲染
- ✅ Markdown 安全渲染（XSS 防护）
- ✅ PDF 在线预览
- ✅ 历史对话记录管理
- ✅ 医学影像查看器与对比分析

## 项目结构

```
frontend/
├── src/
│   ├── api/              # API 接口定义
│   │   ├── profile.js    # 画像相关接口
│   │   ├── resource.js   # 资源生成相关接口
│   │   ├── tutor.js      # 智能辅导相关接口
│   │   ├── learningPath.js # 学习路径相关接口
│   │   ├── assessment.js # 评估相关接口
│   │   ├── user.js       # 用户相关接口
│   │   └── medical.js    # 医学影像相关接口
│   ├── components/       # 组件
│   │   ├── form/         # 表单组件（登录/注册）
│   │   ├── svg/          # SVG 图标组件
│   │   ├── AvatarUpload.vue
│   │   ├── UserDialog.vue
│   │   ├── LoadingSpinner.vue
│   │   ├── ThinkingPanel.vue    # AI 思考过程面板
│   │   ├── MedicalImageViewer.vue # 医学影像查看器
│   │   └── ImageUpload.vue      # 图片上传组件
│   ├── router/           # 路由配置
│   ├── stores/           # Pinia 状态管理（用户/主题）
│   ├── styles/           # 样式（变量/过渡动画/公共样式）
│   ├── utils/            # 工具函数（请求封装/图片压缩/流式暂停）
│   ├── views/            # 页面视图
│   │   ├── login.vue     # 登录页
│   │   ├── home.vue      # 首页
│   │   ├── profile.vue   # 学习画像页
│   │   ├── resource.vue  # 资源生成页
│   │   ├── tutor.vue     # 智能辅导页
│   │   ├── learningPath.vue # 学习路径页
│   │   └── assessment.vue   # 学习评估页
│   ├── App.vue
│   └── main.js
├── public/               # 静态资源
│   └── videos/           # 视频资源（登录背景等）
├── dist/                 # 构建输出
└── vite.config.js        # Vite 配置
```

## 环境要求

- Node.js: `^20.19.0 || >=22.12.0`
- npm 或 yarn

## 快速启动

```bash
# 1. 进入前端目录
cd frontend

# 2. 安装依赖
npm install

# 3. 启动开发服务器
npm run dev
```

项目将在 `http://localhost:5173` 启动，并自动打开浏览器。

## 构建生产版本

```bash
npm run build
```

构建产物输出到 `dist/` 目录。

## 预览生产构建

```bash
npm run preview
```

## 开发脚本

| 命令 | 说明 |
|:---|:---|
| `npm run dev` | 启动开发服务器 |
| `npm run build` | 构建生产版本 |
| `npm run preview` | 预览生产构建 |
| `npm run lint` | 运行 ESLint 并自动修复 |
| `npm run format` | 使用 Prettier 格式化代码 |

## 代理配置

开发环境下，Vite 自动代理以下路径到后端服务（`http://localhost:8080`）：

- `/api` — 后端 REST API
- `/uploads` — 文件上传资源

详见 `vite.config.js` 中的 `server.proxy` 配置。