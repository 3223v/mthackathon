# 活动规划 Agent 系统

基于 LangGraph 的智能出行规划助手，支持多场景活动规划、实时流式对话、三种重规划模式和事务式下单。

---

## 功能特性

- 🤖 **智能规划**：基于 LLM 的智能活动规划生成
- 📊 **多场景支持**：亲子出行、朋友聚会、个人旅行
- 🔄 **重规划模式**：替换单活动、部分重规划、全量重规划
- 💬 **流式对话**：WebSocket 实时流式输出
- 📝 **事务下单**：验证→执行→回滚的事务保证
- 🗺️ **交通规划**：自动计算活动间交通方式和时间

---

## 项目结构

```
mthackathon/
├── program/
│   ├── backend/                    # 后端服务
│   │   ├── main.py                 # FastAPI 入口
│   │   ├── agent/                  # LangGraph 图定义
│   │   │   ├── graph.py            # 图构建与 LLM 管理
│   │   │   ├── state.py            # 状态定义
│   │   │   └── nodes/              # 节点实现
│   │   ├── core/                   # 核心工具
│   │   │   ├── travel.py           # 交通计算
│   │   │   └── skill_loader.py     # Skill 加载器
│   │   ├── tools/                  # 工具封装
│   │   │   ├── query_tools.py      # 查询工具
│   │   │   └── execute_tools.py    # 执行工具
│   │   ├── mockfunction/           # Mock 数据访问层
│   │   ├── mockdata/               # Mock 数据
│   │   ├── skills/                 # 场景 Skill
│   │   ├── config/                 # 配置文件
│   │   ├── data/                   # 运行时数据
│   │   └── doc/                    # 项目文档
│   └── frontend/                   # 前端应用
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

支持配置多个 LLM，系统会自动轮询。

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

#### 1. 安装依赖

```bash
cd program/frontend
npm install
```

#### 2. 启动开发服务器

```bash
npm run dev
```

#### 3. 构建生产版本

```bash
npm run build
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
```

**接收消息：**
```json
{"type": "chunk", "content": "正在为您规划..."}
{"type": "plan", "content": [...], "plan_id": "plan_xxx"}
{"type": "ai_message", "content": "您的出游方案已生成..."}
```

### REST API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/orders/validate` | POST | 验证订单可用性 |
| `/api/orders/execute` | POST | 批量执行订单 |
| `/api/orders/execute/{index}` | POST | 单独执行订单 |
| `/api/plan/alternatives` | POST | 生成 Top-K 替代方案 |
| `/api/plan/reroute` | POST | 用户选择路径后重新计算 |
| `/health` | GET | 健康检查 |

---

## 配置说明

### LLM 配置 (`config/llm_config.json`)

支持多个 LLM 配置，系统会自动轮询：

```json
[
  {
    "name": "LLM名称",
    "model": "模型名称",
    "base_url": "API地址",
    "api_key": "API密钥",
    "temperature": 0.7,
    "max_tokens": 4096
  }
]
```

### Prompt 配置 (`config/prompts.json`)

包含系统提示词、用户提示词和重规划提示词。

### Skill 配置 (`config/skills.json`)

Skill 索引配置，定义场景触发关键词。

---

## 使用示例

### 基本对话

```
用户: 帮我规划明天和家人去北京动物园的行程
Agent: 正在分析需求...
Agent: 匹配到亲子出行场景
Agent: 📋 亲子出行方案
       方案ID: plan_abc123
       ━━━━━━━━━━━━━━━━━━━━
       09:00 - 11:30 | 🎯 北京动物园
         💰 15元 | ⭐4.4
         🔖 需预订: 成人票x2+儿童票x1
       🚕 打车 22分钟 (10km)
       11:52 - 13:30 | 🍽️ 海底捞火锅
         💰 200元
       ━━━━━━━━━━━━━━━━━━━━
       💰 预计总花费: 215元
```

### 重规划

```
用户: 换掉海底捞
Agent: ✅ 已将「海底捞火锅」替换为「四季民福烤鸭店」
```

### 部分重规划

```
用户: 从动物园之后重新规划
Agent: ✅ 已从第1个活动之后重新规划，共4个活动。
```

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

## 开发指南

### 添加新 Skill

1. 在 `skills/` 下创建 `NewSkill/NewSkill.md`
2. 在 `config/skills.json` 中添加索引项
3. 重启后端即可自动加载

### 添加新数据源

1. 在 `mockdata/` 中添加 JSON 文件
2. 在 `mockfunction/__init__.py` 中添加查询函数
3. 在 `tools/query_tools.py` 中添加封装方法

---

## 故障排除

### LLM 服务不可用

确保 `config/llm_config.json` 中配置了有效的 API Key。

### 端口占用

```bash
# 查找占用端口的进程
netstat -ano | findstr :8000
# 结束进程
taskkill /F /PID <PID>
```

### 日志查看

日志文件位于 `logs/agent_YYYYMMDD.log`。

---

## 许可证

MIT License