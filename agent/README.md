# 美团本地活动规划 Agent

> 把事情做完，不只是搜索。

基于 Python + LangGraph 构建的本地场景短时活动规划与执行 Agent。接受一句自然语言目标，输出可执行的完整方案并自动完成关键下单/预订动作。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

编辑 `.env` 文件，填入你的 API Key：

```env
# 必填：OpenAI 格式 API Key（支持 OpenAI / DeepSeek / Qwen 等）
OPENAI_API_KEY=sk-your-key-here

# 可选：备用模型 API Key
DEEPSEEK_API_KEY=sk-your-deepseek-key-here
```

如需切换模型，编辑 `config/llm_config.json`，支持任意 OpenAI 兼容格式的 API。

### 3. 启动

```bash
python main.py
```

## 使用方法

### 规划活动

直接用自然语言描述需求，Agent 会自动分析场景、收集信息、生成方案：

```
💬 你: 今天下午带5岁的孩子出去玩几个小时
🤖 助手: [分析场景 → 生成方案 → 展示时间线和费用]
💬 你: 确认
🤖 助手: [自动下单 → 返回订单号]
```

支持的场景：
- **亲子出行**："带孩子出去玩"、"和家人周末去哪里"
- **朋友聚会**："4个人，2男2女想出去玩"
- **情侣约会**："和女朋友想找个地方逛逛"

### 中途调整

规划过程中可以随时加入新信息，Agent 会重新调整方案：

```
💬 你: 今天下午带孩子出去玩
🤖 助手: [展示方案]
💬 你: 对了，我老婆在减肥
🤖 助手: [自动调整餐厅为清淡健康选项]
💬 你: 确认
🤖 助手: [执行下单]
```

### 偏好设置

通过 `/偏好` 命令管理个人偏好，偏好会跨会话保留：

```
💬 你: /偏好 我喜欢吃火锅，不喜欢吃辣，最远不要超过10公里
🤖 助手: [确认偏好设置，展示当前偏好]

💬 你: /偏好
📋 当前偏好设置：
  喜欢的菜系: 火锅
  不喜欢的菜系: 辣
  最远距离: 10km
```

### 命令列表

| 命令 | 说明 |
|------|------|
| 直接输入 | 自然语言描述需求，Agent 自动规划 |
| `/偏好` | 查看当前偏好设置 |
| `/偏好 [内容]` | 设置/更新偏好 |
| `/reset` | 重置对话状态 |
| `/help` | 显示帮助信息 |
| `/quit` | 退出程序 |

## 项目结构

```
agent/
├── main.py                          # CLI 交互入口
├── requirements.txt                 # Python 依赖
├── .env                             # 环境变量配置（API Key）
│
├── config/                          # 配置层
│   ├── __init__.py                  #   LLM 配置 + 提示词加载
│   ├── llm_config.json              #   LLM 模型配置（支持多个模型）
│   └── prompts.json                 #   提示词模板（集中管理，方便调优）
│
├── agent/                           # Agent 核心层
│   ├── core.py                      #   LangGraph 状态图定义 + 所有节点逻辑
│   ├── state.py                     #   AgentState 状态数据结构
│   └── preferences.py               #   用户偏好管理（增删改查 + 持久化）
│
├── tools/                           # 工具层
│   ├── query.py                     #   查询工具（景点/餐厅/活动/蛋糕/鲜花）
│   └── book.py                      #   预订工具（门票/餐厅/活动/电影/蛋糕/鲜花）
│
├── mock/                            # Mock 数据层
│   ├── attractions.json             #   景点数据（8个）
│   ├── restaurants.json             #   餐厅数据（8家）
│   ├── activities.json              #   活动数据（10种）
│   ├── cakes_flowers.json           #   蛋糕/鲜花数据
│   └── orders.json                  #   订单模板定义
│
├── skills/                          # Skill 定义层
│   ├── Parent-ChildTravelPlanning/  #   亲子出行 Skill
│   ├── FriendsOuting/               #   朋友出行 Skill
│   └── PersonalTravelPlanning/      #   情侣/个人出行 Skill
│
├── utils/                           # 工具函数
│   └── helpers.py                   #   JSON 读写、金额格式化、数据过滤
│
├── doc/                             # 技术文档
│   ├── planning.md                  #   规划策略详解
│   ├── toolchain.md                 #   工具调用链路
│   └── error-handling.md            #   异常处理机制
│
└── data/                            # 运行时数据（自动生成）
    ├── preferences.json             #   用户偏好持久化
    └── orders.json                  #   订单记录持久化
```

## 三大机制

### 1. 偏好机制

用户可以通过 `/偏好` 主动告诉 Agent 喜欢什么，也可以在对话中自然提及（如"我老婆在减肥"），Agent 会自动提取并持久化。下次规划时自动参考。

支持的偏好类型：喜欢的菜系、不喜欢的菜系、饮食限制、活动类型、最远距离、预算、同行人。

### 2. 引导机制（打断）

Agent 在规划过程中可以被用户随时打断加入新信息。Agent 将过往信息和新信息一同分析，评估影响程度后重新调整方案。

### 3. Skill 机制

Agent 根据用户输入自动分析场景类型并选择对应的 Skill：
- 亲子场景 → Parent-ChildTravelPlanning
- 朋友场景 → FriendsOuting
- 情侣/个人 → PersonalTravelPlanning

Skill 定义为标准 Markdown 格式，包含触发条件、能力清单、输出模板等。

## 提示词管理

所有 LLM 提示词集中存放在 `config/prompts.json`，方便独立调优，无需修改代码。

## 技术文档

- [规划策略](doc/planning.md) - 分析、补全、规划、确认、执行的五阶段流程
- [工具调用链路](doc/toolchain.md) - 查询层和执行层的完整调用链
- [异常处理机制](doc/error-handling.md) - LLM 解析、信息缺失、API 故障等场景的处理策略
