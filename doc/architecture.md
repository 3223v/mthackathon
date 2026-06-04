# 系统架构设计文档

## 概述

活动规划 Agent 系统是一个基于 LangGraph 的智能出行规划助手，支持多场景活动规划、实时流式对话、三种重规划模式和事务式下单。

---

## 系统架构

```
┌─────────────────────────────────────────────────┐
│                    前端 (WebSocket + REST)        │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│                  main.py (FastAPI)                │
│  ┌──────────────┐  ┌───────────────────────────┐ │
│  │ /ws/chat     │  │ /api/orders/*  (REST API) │ │
│  │ WebSocket    │  │ validate/execute/pending  │ │
│  └──────┬───────┘  └───────────┬───────────────┘ │
└─────────┼──────────────────────┼─────────────────┘
          │                      │
┌─────────▼──────────────────────▼─────────────────┐
│                agent/graph.py                     │
│  ┌─────────────────────────────────────────────┐ │
│  │          LangGraph StateGraph                │ │
│  │                                              │ │
│  │  analyze_intent ─┬─ general_response → END   │ │
│  │                  ├─ extract_preferences → END│ │
│  │                  ├─ extract_prefs → query    │ │
│  │                  │     → planner → END       │ │
│  │                  ├─ replace_activity → END   │ │
│  │                  ├─ partial_replan → END     │ │
│  │                  └─ full_replan → query → END│ │
│  └─────────────────────────────────────────────┘ │
│  ┌──────────────┐  ┌───────────────────────────┐ │
│  │  LLMManager  │  │  MemorySaver (会话状态)    │ │
│  │  流式+重试   │  │                           │ │
│  └──────────────┘  └───────────────────────────┘ │
└──────────────────────────────────────────────────┘
          │
┌─────────▼────────────────────────────────────────┐
│                  agent/nodes/                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ intent   │ │preferences│ │     query        │  │
│  │ 意图分类 │ │ 偏好提取  │ │  数据查询        │  │
│  │ +Skill   │ │ 持久化    │ │  via mockfunction│  │
│  └──────────┘ └──────────┘ └──────────────────┘  │
│  ┌──────────────────┐ ┌──────────────────────┐   │
│  │     planner      │ │     replanner        │   │
│  │  LLM 规划生成     │ │  替换/部分/全量       │   │
│  │  结构化JSON输出   │ │  约束求解            │   │
│  └──────────────────┘ └──────────────────────┘   │
└──────────────────────────────────────────────────┘
          │
┌─────────▼────────────────────────────────────────┐
│                    core/                           │
│  ┌──────────────────┐ ┌──────────────────────┐   │
│  │    travel.py     │ │   skill_loader.py    │   │
│  │  Haversine距离   │ │   Skill解析+匹配     │   │
│  │  4种交通模式     │ │   skills/*.md        │   │
│  └──────────────────┘ └──────────────────────┘   │
└──────────────────────────────────────────────────┘
          │
┌─────────▼────────────────────────────────────────┐
│               mockfunction/                        │
│  ┌──────────────────────────────────────────────┐ │
│  │  数据查询 (附近景点/餐厅/活动/饮品/商超)       │ │
│  │  可用性查询 (餐厅/活动预约)                   │ │
│  │  预订执行 (餐厅/门票/配送)                    │ │
│  │  用户偏好 (持久化到 data/preferences.json)    │ │
│  └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
          │
┌─────────▼────────────────────────────────────────┐
│                mockdata/ (7个JSON文件)             │
│  attractions.json  restaurants.json  activities   │
│  cafes.json  shops.json  groceries.json  others   │
└──────────────────────────────────────────────────┘
```

---

## 核心设计决策

### 1. 为什么用 LangGraph？

- **状态管理**：AgentState 在节点间流转，MemorySaver 支持跨轮次持久化
- **条件路由**：根据意图类型路由到不同处理分支
- **可扩展**：新增节点只需注册 + 添加路由规则

### 2. Skills 机制

Skill 是场景化的规划指导文件（`skills/*.md`），包含：
- 触发条件（关键词匹配）
- 输入参数（如孩子年龄、团体人数）
- 业务流程（规划步骤）
- 能力清单（需要调用哪些查询）
- 输出模板（方案展示格式）
- 注意事项（场景特定约束）

**加载流程**：
1. 系统启动 → `SkillLoader.load_all()` 解析所有 `.md` 文件
2. 用户输入 → `skill_loader.match_skill()` 按关键词匹配
3. 匹配到的 Skill → 注入 Planner Node 的 System Prompt

### 3. 交通计算

使用 Haversine 球面距离公式，四种交通模式：

| 模式 | 速度 | 适合距离 | 固定开销 |
|------|------|----------|----------|
| 步行 | 5 km/h | 0-1.5km | 无 |
| 公共交通 | 25 km/h | 1-30km | +8min（等车/走路） |
| 打车 | 35 km/h | 1.5-50km | +5min（等车） |
| 自驾 | 30 km/h | 2-100km | +8min（取车/停车） |

### 4. 流式输出

LLM 调用时通过 `astream` 实现 token 级流式输出：
- `LLMManager.invoke()` 接受 `stream_callback` 参数
- 回调函数通过 LangGraph 的 `config.configurable.stream_callback` 传递
- 前端接收 `chunk` 事件实现打字机效果

### 5. 下单事务

```
POST /api/orders/execute
  ├─ 阶段1: 收集 plan 中所有 pre_book.need=true 的活动
  ├─ 阶段2: 逐个验证可用性
  │   └─ 任一失败 → 返回失败，不执行任何订单
  └─ 阶段3: 全部通过 → 依次执行
      └─ 任一失败 → 回滚已执行的订单
```

---

## 数据流

### 规划流程

```
用户输入
  → analyze_intent: 分类 (planning) + 匹配 Skill
  → extract_preferences: 提取偏好，持久化到 data/preferences.json
  → query_data: 根据 Skill filter 调用 mockfunction 查询
  → planner: LLM 生成结构化 JSON plan
  → 返回前端: chunk 流 + plan JSON + ai_message
```

### 重规划流程

```
用户输入（已有 plan）
  → analyze_intent: 分类 (replan_replace)
  → replace_activity:
      1. 定位目标活动
      2. 计算约束（时间/位置）
      3. 查询替代数据
      4. 选择最优 → 更新 plan
      5. 重算交通 → 返回更新后 plan
```

### 偏好持久化流程

```
用户输入（含个人信息）
  → extract_preferences:
      1. 正则提取：姓名/年龄/位置/饮食/预算/社会关系
      2. 合并已有偏好（从 data/preferences.json 读取）
      3. 写入 data/preferences.json
      4. 通知用户（preference_update 事件）
```

---

## 状态结构 (AgentState)

```python
class AgentState(TypedDict):
    messages: Sequence[BaseMessage]     # 对话历史（operator.add 追加）
    preferences: str                    # 偏好文本摘要
    user_profile: Dict                  # 结构化用户画像
    intent_type: str                    # general|planning|replan_*
    skill_context: Optional[Dict]       # 匹配的 Skill 完整内容
    plan: List[Dict]                    # 当前规划方案
    plan_id: str                        # 方案 ID
    query_results: Dict                 # 查询结果缓存
    replan_target: Dict                 # 重规划目标
    interrupted: bool                   # 中断标志
    conversation_id: str                # 会话 ID
    context: Dict                       # 额外上下文
```

---

## LLM 调用策略

### 双池设计
系统初始化时每个 LLM 配置创建两个实例：
- **流式池** (`self.llms`, `streaming=True`)：前端实时 token 推送
- **非流式池** (`self.ns_llms`, `streaming=False`)：结构化输出、校验、重试

### 调用策略
1. **多 LLM 轮询**：两个池各自独立轮询，失败自动切换
2. **自动重试**：单个 LLM 失败后最多重试 3 次，间隔递增
3. **流式优先**：规划类首次调用使用流式模式，重试使用非流式结构化输出
4. **三层结构化输出保底**：
   - **Layer 1**: Native `json_schema` + `strict=True`（OpenAI 原生结构化输出）
   - **Layer 2**: Function Calling + `tool_choice="required"`（兼容其他模型）
   - **Layer 3**: 返回 None → 调用方降级到文本解析
5. **流式 + 后置校验 + 倒计时重试**：
   - 首次流式输出到前端 → 完成后 `_parse_plan_json()` 校验 JSON
   - 解析失败 → WebSocket 发送 `plan_validation_failed` 事件（3秒倒计时）
   - 前端显示琥珀色横幅 + 手动重试按钮
   - 重试时直接调用 `generate_plan()`（非流式结构化输出），不重新执行整张图
6. **日志记录**：控制台 INFO 截取展示（200字），文件 DEBUG 全量保存

---

## 文件组织

```
backend/
├── main.py                  # FastAPI 入口（WebSocket + REST API）
├── agent/
│   ├── graph.py             # LangGraph 图定义 + LLMManager（含结构化输出）
│   ├── state.py             # AgentState 类型定义
│   ├── schemas.py           # Pydantic 结构化输出 Schema 定义
│   └── nodes/
│       ├── intent.py        # 意图分析 + Skill 匹配
│       ├── preferences.py   # 偏好提取 + 持久化
│       ├── query.py         # 数据查询
│       ├── planner.py       # 核心规划生成
│       └── replanner.py     # 三种重规划
├── core/
│   ├── travel.py            # 交通时间计算
│   └── skill_loader.py      # Skill 加载器
├── tools/
│   ├── query_tools.py       # 查询工具（封装 mockfunction）
│   └── execute_tools.py     # 执行工具（预订/下单）
├── mockfunction/            # Mock 数据访问层
├── mockdata/                # Mock 数据（7个JSON）
├── skills/                  # 3个 Skill Markdown 文件
├── config/
│   ├── llm_config.json      # LLM 配置
│   ├── prompts.json         # Prompt 模板
│   └── skills.json          # Skill 索引
├── data/
│   └── preferences.json     # 用户偏好持久化
├── doc/
│   ├── api-guide.md         # 前端对接指南
│   └── architecture.md      # 本文档
└── utils/
    └── logger.py            # 日志系统
```

---

### 路径选择（二维矩阵）

```
POST /api/plan/matrix
  → 返回 matrix[列][行]（每列=plan中的一个位置，含交通节点）
  → 每行=原始方案 + Top-K 替代方案
  → 交通节点也有替代（不同模式）

前端 MatrixView 覆盖层：
  → 用户每列选一个节点
  → POST /api/plan/reroute-matrix
  → 返回完整 plan（含重算的交通）
  → CustomEvent 回调 → ChatInterface 更新方案
```

矩阵视图在当前页面内以全屏覆盖层打开，WebSocket 保持连接，不丢失会话状态。

---

## 扩展指南

### 添加新 Skill

1. 在 `skills/` 下创建 `NewSkill/NewSkill.md`
2. 在 `config/skills.json` 中添加索引项
3. 重启后端即可自动加载

### 添加新的数据源

1. 在 `mockdata/` 中添加 JSON 文件
2. 在 `mockfunction/__init__.py` 中添加查询函数
3. 在 `tools/query_tools.py` 中添加封装方法

### 添加新的交通模式

在 `core/travel.py` 的 `TRANSPORT_MODES` 字典中添加条目即可。
