# 活动规划 Agent 系统

基于 LangGraph 的智能出行规划助手，支持多场景活动规划、实时流式对话、三种重规划模式、事务式下单、矩阵路径选择。

---

## 功能特性

- 🤖 **智能规划**：基于 LLM 的智能活动规划生成，支持三层结构化输出（json_schema → function_calling → 文本解析）
- 📊 **多场景支持**：亲子出行、朋友聚会、情侣/个人旅行
- 🔄 **重规划模式**：替换单活动、部分重规划、全量重规划
- 💬 **流式对话**：WebSocket 实时流式输出，后置 JSON 校验 + 倒计时自动重试
- 📝 **事务下单**：验证 → 执行 → 回滚的事务保证
- 🗺️ **交通规划**：自动计算活动间交通方式和时间，支持前端实时切换交通模式
- 🔗 **矩阵路径选择**：二维矩阵视图，每列一个节点位置（含交通），横向切换替代方案，点击连线选择路径
- 🎯 **替代方案轮播**：活动卡片右侧箭头一键切换替代方案，支持本地交通模式切换

---

## 项目结构

```
mthackathon/
├── program/
│   ├── backend/                    # 后端服务
│   │   ├── main.py                 # FastAPI 入口（WebSocket + REST）
│   │   ├── agent/                  # LangGraph 图定义
│   │   │   ├── graph.py            # 图构建 + LLMManager（双池：流式+非流式）
│   │   │   ├── state.py            # AgentState 状态定义
│   │   │   ├── schemas.py          # Pydantic 结构化输出 Schema
│   │   │   └── nodes/              # 节点实现
│   │   │       ├── intent.py       # 意图分析 + Skill 匹配
│   │   │       ├── preferences.py  # 偏好提取 + 持久化
│   │   │       ├── query.py        # 数据查询
│   │   │       ├── planner.py      # 核心规划（流式+后置校验+结构化重试）
│   │   │       ├── replanner.py    # 三种重规划
│   │   │       └── alternatives.py # DAG 替代方案 + 二维矩阵生成
│   │   ├── core/                   # 核心工具
│   │   │   ├── travel.py           # 交通计算（Haversine + 4种模式）
│   │   │   └── skill_loader.py     # Skill 加载器
│   │   ├── tools/                  # 工具封装
│   │   │   ├── query_tools.py      # 查询工具
│   │   │   └── execute_tools.py    # 执行工具
│   │   ├── mockfunction/           # Mock 数据访问层
│   │   ├── mockdata/               # Mock 数据（7个JSON）
│   │   ├── skills/                 # 场景 Skill（3个Markdown）
│   │   ├── config/                 # 配置文件
│   │   ├── data/                   # 运行时数据
│   │   └── utils/                  # 日志系统（控制台截取+文件全量）
│   └── frontend/                   # Next.js 16 + React 19 + TailwindCSS 4
│       ├── app/
│       │   ├── page.tsx            # 主页面
│       │   ├── layout.tsx          # 布局
│       │   └── globals.css         # 全局样式
│       └── components/
│           ├── ChatInterface.tsx   # 三栏聊天界面 + 覆盖层
│           └── MatrixView.tsx      # 矩阵路径选择覆盖层
├── doc/                            # 项目文档
└── README.md
```

---

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+（前端）
- OpenAI API Key（或其他支持的 LLM API）

### 后端部署

#### 1. 安装依赖

```bash
cd program/backend
pip install -r requirements.txt
```

#### 2. 配置 LLM

编辑 `config/llm_config.json`：

```json
[
  {
    "name": "OpenAI",
    "model": "gpt-4o",
    "base_url": "https://api.openai.com/v1",
    "api_key": "your-api-key",
    "temperature": 0.7,
    "max_tokens": 4096
  }
]
```

支持配置多个 LLM，系统自动轮询。后端启动时会同时创建流式池和非流式池。

#### 3. 启动服务

```bash
# 开发模式
python main.py

# 或使用 uvicorn
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

服务启动后访问：
- WebSocket: `ws://localhost:8000/ws/chat`
- REST API: `http://localhost:8000/`
- 健康检查: `http://localhost:8000/health`

### 前端部署

```bash
cd program/frontend
npm install
npm run dev          # 开发服务器
npm run build        # 生产构建
```

---

## API 接口

### WebSocket 端点

| 端点 | 说明 |
|------|------|
| `ws://localhost:8000/ws/chat` | 实时聊天接口 |

#### 消息格式

**发送消息：**
```json
{"type": "message", "content": "帮我规划周末出游"}
{"type": "interrupt", "content": "预算控制在500以内"}
{"type": "retry"}                    // 手动重试
{"type": "retry_planner"}            // 立即重试规划（跳过倒计时）
```

**接收消息：**
```json
{"type": "chunk", "content": "正在为您规划..."}
{"type": "plan", "content": [...], "plan_id": "plan_xxx"}
{"type": "plan_updated", "content": [...], "plan_id": "plan_xxx"}
{"type": "plan_validation_failed", "countdown": 3, "message": "方案解析异常，3秒后自动重新生成..."}
{"type": "ai_message", "content": "您的出游方案已生成..."}
{"type": "done", "plan_id": "plan_xxx", "plan": [...]}
{"type": "error", "code": "...", "message": "...", "retry": true}
```

### REST API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/orders/validate` | POST | 验证订单可用性 |
| `/api/orders/execute` | POST | 批量执行订单（事务式） |
| `/api/orders/execute/{index}` | POST | 单独执行订单 |
| `/api/plan/alternatives` | POST | 生成 Top-K 替代方案 DAG |
| `/api/plan/matrix` | POST | 生成二维矩阵（含交通节点替代） |
| `/api/plan/reroute` | POST | 用户选择 DAG 路径后重新计算 |
| `/api/plan/reroute-matrix` | POST | 用户选择矩阵路径后重新计算 |
| `/health` | GET | 健康检查 |

---

## 核心机制

### 三层结构化输出

LLM 输出采用三层保底策略（`LLMManager.invoke_structured()`）：

1. **Layer 1**: Native `json_schema` + `strict=True`（OpenAI 原生结构化输出）
2. **Layer 2**: `function_calling` + `tool_choice`（兼容其他模型）
3. **Layer 3**: 返回 `None`，调用方降级到文本解析

### 流式 + 后置校验 + 倒计时重试

规划节点（planner）的完整流程：

1. 首次使用流式 LLM → 前端实时显示 token
2. 输出完成后 `_parse_plan_json()` 校验 JSON
3. 解析失败 → 前端显示琥珀色倒计时横幅（3秒）+ 手动重试按钮
4. 重试时直接调用 planner（非流式结构化输出），不重新执行整张图

### 矩阵路径选择

- 二维矩阵：横向是 plan 中的每个节点（活动+交通），纵向是原始方案+替代方案
- 通过 `MatrixView` 覆盖层在当前页面内打开，WebSocket 保持连接
- 每列点击一个节点，选中路径通过 CustomEvent 回调更新主界面
- 交通节点有独立的交通方式替代（步行/打车/公交/自驾）

### 方案面板替代切换

- 活动卡片右侧 ▲/▼ 箭头切换替代方案（调用 `/api/plan/reroute`）
- 交通卡片右侧 ▲/▼ 箭头切换交通模式（前端本地计算 Haversine）
- 切换时卡片有加载遮罩，底部预订栏始终可见

---

## 配置说明

### LLM 配置 (`config/llm_config.json`)

支持多个 LLM，系统自动轮询。后端启动时每个配置创建两个实例（流式+非流式）。

### Prompt 配置 (`config/prompts.json`)

包含系统提示词、用户提示词和重规划提示词。

### Skill 配置 (`config/skills.json`)

Skill 索引配置，定义场景触发关键词。新增 Skill 后重启即可自动加载。

---

## 开发指南

### 添加新 Skill

1. 在 `skills/` 下创建 `NewSkill/NewSkill.md`
2. 在 `config/skills.json` 中添加索引项
3. 重启后端即可自动加载

### 添加新数据源

1. 在 `mockdata/` 中添加 JSON 文件
2. 在 `mockfunction/__init__.py` 中添加查询函数
3. 在 `tools/query_tools.py` 中添加封装方法

### 添加新交通模式

在 `core/travel.py` 的 `TRANSPORT_MODES` 字典中添加条目即可。

---

## 文档目录

| 文档 | 说明 |
|------|------|
| `doc/architecture.md` | 系统架构设计 |
| `doc/api-guide.md` | 前端对接指南 |
| `doc/planning-strategy.md` | 规划策略详解 |
| `doc/tool-call-chain.md` | 工具调用链路 |
| `doc/error-handling.md` | 异常处理机制 |

---

## 许可证

MIT License
