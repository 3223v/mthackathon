# 工具调用链路文档

## 概述

本文档详细描述活动规划 Agent 系统中的工具调用链路，包括查询工具、执行工具的调用流程、数据流转和接口规范。

---

## 一、工具架构

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent Layer                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ intent   │ │preferences│ │  planner │ │ replanner│          │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘          │
└───────┼───────────┼───────────┼───────────┼───────────────────┘
        │           │           │           │
┌───────▼───────────▼───────────▼───────────▼───────────────────┐
│                       Tools Layer                               │
│  ┌─────────────────────┐ ┌─────────────────────────────────┐   │
│  │    QueryTools       │ │         ExecuteTools            │   │
│  │  (数据查询)         │ │       (预订/下单/偏好保存)       │   │
│  └──────────┬──────────┘ └──────────────────┬──────────────┘   │
└─────────────┼───────────────────────────────┼──────────────────┘
              │                               │
┌─────────────▼───────────────────────────────▼──────────────────┐
│                     Mock Function Layer                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  mockfunction/__init__.py  (数据访问层)                   │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
              │
┌─────────────▼──────────────────────────────────────────────────┐
│                        Data Layer                              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  mockdata/*.json  (景点/餐厅/活动/饮品等7个JSON文件)     │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 调用层次

| 层次 | 职责 | 文件位置 |
|------|------|----------|
| **Agent 层** | 业务逻辑编排，调用工具 | `agent/nodes/` |
| **Tools 层** | 工具封装，参数校验 | `tools/` |
| **Mock Function 层** | 数据访问，业务逻辑实现 | `mockfunction/` |
| **Data 层** | 数据存储 | `mockdata/` |

---

## 二、查询工具链路

### 2.1 查询工具分类

#### 2.1.1 附近查询工具

| 工具方法 | 功能 | 数据源 | 半径默认值 |
|----------|------|--------|------------|
| `query_nearby_attractions` | 查询附近景点 | `attractions.json` | 20km |
| `query_nearby_restaurants` | 查询附近餐厅 | `restaurants.json` | 15km |
| `query_nearby_activities` | 查询附近活动 | `activities.json` | 15km |
| `query_nearby_cafes` | 查询附近饮品店 | `cafes.json` | 10km |

#### 2.1.2 场景推荐工具

| 工具方法 | 功能 | 适用场景 |
|----------|------|----------|
| `query_family_friendly` | 查询亲子友好场所 | 亲子出行 |
| `query_group_friendly` | 查询团体友好场所 | 朋友聚会 |
| `query_romantic` | 查询浪漫场所 | 情侣约会 |
| `recommend_by_scenario` | 根据场景推荐 | 通用场景 |

#### 2.1.3 可用性查询工具

| 工具方法 | 功能 | 参数 |
|----------|------|------|
| `check_restaurant_available` | 检查餐厅可用性 | `restaurant_id`, `date`, `time`, `people` |
| `check_activity_available` | 检查活动可用性 | `activity_id`, `date`, `time` |

### 2.2 查询工具调用流程

#### 2.2.1 数据查询节点调用

```python
# agent/nodes/query.py
async def query_data(state: AgentState) -> Dict[str, Any]:
    skill_context = state.get("skill_context")
    user_profile = state.get("user_profile", {})
    
    # 构建过滤器
    filters = _build_filters(skill_context, user_profile)
    
    # 调用查询工具
    query_tools = QueryTools()
    results = query_tools.query_by_filters(
        lat=user_profile.get("location", {}).get("lat", 39.9042),
        lng=user_profile.get("location", {}).get("lng", 116.4074),
        filters=filters,
    )
    
    return {"query_results": results}
```

#### 2.2.2 过滤器构建逻辑

```python
def _build_filters(skill_context: Dict, user_profile: Dict) -> Dict:
    """根据 Skill 和用户画像构建查询过滤器"""
    filters = {}
    
    # 根据场景设置适合人群
    scenario = skill_context.get("scenario", "")
    suitable_for = []
    if scenario == "family":
        suitable_for.append("family")
    elif scenario == "friends":
        suitable_for.append("group")
    elif scenario == "couple":
        suitable_for.append("couple")
    
    # 根据用户偏好设置标签
    preferences = user_profile.get("preferences", {})
    tags = preferences.get("activity_tags", [])
    
    filters["attractions"] = {"suitable_for": suitable_for, "tags": tags}
    filters["restaurants"] = {"suitable_for": suitable_for}
    filters["activities"] = {"suitable_for": suitable_for}
    filters["cafes"] = {"suitable_for": suitable_for}
    
    return filters
```

#### 2.2.3 查询结果结构

```python
{
    "attractions": [...],      # 景点列表
    "restaurants": [...],      # 餐厅列表
    "activities": [...],       # 活动列表
    "cafes": [...],            # 饮品店列表
}
```

---

## 三、执行工具链路

### 3.1 执行工具分类

#### 3.1.1 预订工具

| 工具方法 | 功能 | 返回结构 |
|----------|------|----------|
| `book_restaurant` | 预订餐厅桌位 | `{"booking_id": "...", "status": "confirmed"}` |
| `book_ticket` | 购买景点门票 | `{"order_id": "...", "status": "confirmed"}` |
| `order_delivery` | 订购配送服务 | `{"delivery_id": "...", "status": "confirmed"}` |

#### 3.1.2 订单管理工具

| 工具方法 | 功能 |
|----------|------|
| `confirm_order` | 确认单个订单 |
| `cancel_order` | 取消订单 |
| `get_pending_orders` | 获取待确认订单列表 |
| `confirm_plan` | 确认方案下所有订单 |

#### 3.1.3 用户偏好工具

| 工具方法 | 功能 |
|----------|------|
| `save_preferences` | 保存用户偏好 |
| `get_preferences` | 获取用户偏好 |
| `update_family_info` | 更新家庭信息 |
| `update_friends_info` | 更新朋友信息 |

### 3.2 事务式下单流程

#### 3.2.1 批量下单调用链

```
POST /api/orders/execute
    │
    ├─ 阶段1: 收集待下单项
    │   └─ 遍历 plan 中所有 pre_book.need=True 的活动
    │
    ├─ 阶段2: 验证可用性
    │   ├─ check_restaurant_availability()
    │   └─ check_activity_availability()
    │   └─ 任一失败 → 返回失败，不执行任何订单
    │
    └─ 阶段3: 执行订单
        ├─ book_restaurant() / book_ticket() / order_delivery()
        └─ 任一失败 → 回滚已执行订单
```

#### 3.2.2 事务保证机制

```python
# main.py - execute_all_orders
async def execute_all_orders(payload: PlanForOrder):
    # 阶段1: 收集
    pending_orders = _collect_pending_items(payload.plan)
    
    # 阶段2: 验证
    validation = await validate_orders(payload)
    if not validation["all_valid"]:
        return {"success": False, "validation": validation}
    
    # 阶段3: 执行
    order_results = []
    for order_info in pending_orders:
        try:
            result = _execute_single_order(order_info, payload)
            order_results.append(result)
        except Exception as e:
            # 回滚
            await _rollback_orders(order_results)
            return {"success": False, "message": str(e)}
    
    return {"success": True, "orders": order_results}
```

---

## 四、数据流转链路

### 4.1 规划流程数据流转

```
用户输入 (WebSocket)
    │
    ▼
┌─────────────────────────────────────────────┐
│ analyze_intent (意图分析)                    │
│   ├─ 识别意图类型                            │
│   └─ 匹配 Skill                             │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│ extract_preferences (偏好提取)               │
│   ├─ 提取用户信息                            │
│   └─ 持久化到 preferences.json               │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│ query_data (数据查询)                        │
│   ├─ QueryTools.query_by_filters()          │
│   ├─ mockfunction.get_nearby_*()            │
│   └─ 返回 query_results                     │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│ planner (规划生成)                           │
│   ├─ LLM 生成 JSON 方案                     │
│   ├─ _insert_transport_activities()         │
│   └─ 返回 plan + ai_message                 │
└─────────────────────────────────────────────┘
    │
    ▼
前端展示 (WebSocket: plan + ai_message)
```

### 4.2 替换活动数据流转

```
用户请求: "换掉海底捞"
    │
    ▼
┌─────────────────────────────────────────────┐
│ analyze_intent → replan_replace             │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│ replace_activity (替换活动)                   │
│   ├─ _find_target_activity() 定位目标        │
│   ├─ _calculate_constraints() 计算约束      │
│   ├─ _query_alternatives() 查询替代        │
│   │   └─ QueryTools.query_nearby_*()       │
│   ├─ _select_best_alternative() 选择最优    │
│   └─ _recalculate_affected_transport()     │
└─────────────────────────────────────────────┘
    │
    ▼
前端展示 (WebSocket: plan_updated)
```

---

## 五、接口规范

### 5.1 查询工具接口

#### 5.1.1 `query_by_filters`

**参数**:
```python
{
    "lat": float,                    # 纬度，默认 39.9042
    "lng": float,                    # 经度，默认 116.4074
    "filters": {                     # 过滤器
        "attractions": {
            "suitable_for": List[str],  # 适合人群: family/group/couple
            "tags": List[str],          # 标签过滤
        },
        "restaurants": {
            "suitable_for": List[str],
            "cuisine": str,             # 菜系
        },
        "activities": {
            "suitable_for": List[str],
        },
        "cafes": {
            "suitable_for": List[str],
        },
    }
}
```

**返回**:
```python
{
    "attractions": List[Dict],   # 景点列表
    "restaurants": List[Dict],   # 餐厅列表
    "activities": List[Dict],    # 活动列表
    "cafes": List[Dict],         # 饮品店列表
}
```

### 5.2 执行工具接口

#### 5.2.1 `book_restaurant`

**参数**:
```python
{
    "restaurant_id": str,      # 餐厅ID
    "date": str,               # 日期 (YYYY-MM-DD)
    "time": str,               # 时间 (HH:MM)
    "people": int,             # 用餐人数
    "customer_name": str,      # 客户姓名
    "phone": str,              # 联系电话
    "plan_id": str,            # 关联方案ID
}
```

**返回**:
```python
{
    "code": int,                  # 0 成功，非0 失败
    "message": str,               # 提示信息
    "data": {
        "booking_id": str,         # 预订ID
        "restaurant_id": str,      # 餐厅ID
        "date": str,              # 日期
        "time": str,              # 时间
        "people": int,            # 人数
        "status": str,            # 状态: confirmed/pending
    }
}
```

#### 5.2.2 `book_ticket`

**参数**:
```python
{
    "attraction_id": str,      # 景点ID
    "ticket_type": str,        # 票种: 成人票/儿童票/学生票
    "quantity": int,           # 数量
    "date": str,               # 日期
    "customer_name": str,      # 客户姓名
    "plan_id": str,            # 关联方案ID
}
```

**返回**:
```python
{
    "code": int,                  # 0 成功，非0 失败
    "message": str,               # 提示信息
    "data": {
        "order_id": str,          # 订单ID
        "attraction_id": str,     # 景点ID
        "ticket_type": str,       # 票种
        "quantity": int,          # 数量
        "date": str,              # 日期
        "status": str,            # 状态
    }
}
```

---

## 六、REST API 接口

### 6.1 下单相关接口

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/orders/validate` | POST | 验证订单可用性 |
| `/api/orders/execute` | POST | 批量执行订单 |
| `/api/orders/execute/{index}` | POST | 单独执行订单 |
| `/api/orders/pending/{plan_id}` | GET | 获取待下单列表 |

### 6.2 替代方案接口

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/plan/alternatives` | POST | 生成 Top-K 替代方案 |
| `/api/plan/reroute` | POST | 用户选择路径后重新计算 |

### 6.3 健康检查

| 接口 | 方法 | 功能 |
|------|------|------|
| `/health` | GET | 健康检查 |

---

## 七、WebSocket 消息格式

### 7.1 发送消息

| 类型 | 格式 | 说明 |
|------|------|------|
| `message` | `{"type": "message", "content": "..."}` | 普通消息 |
| `interrupt` | `{"type": "interrupt", "content": "..."}` | 打断/补充 |
| `retry` | `{"type": "retry"}` | 手动重试 |

### 7.2 接收消息

| 类型 | 说明 | 内容结构 |
|------|------|----------|
| `chunk` | LLM 流式 token | `{"content": "..."})` |
| `plan` | 结构化方案 | `{"content": [...], "plan_id": "..."}` |
| `plan_updated` | 方案更新 | `{"content": [...], "plan_id": "..."}` |
| `ai_message` | AI 回复文本 | `{"content": "..."}` |
| `thinking` | 处理进度 | `{"content": "..."}` |
| `skill_detected` | 匹配技能 | `{"content": "...", "skill_id": "..."}` |
| `error` | 错误信息 | `{"code": "...", "message": "...", "retry": true/false}` |

---

## 八、错误处理

### 8.1 工具调用错误

```python
# 工具调用时的错误处理模式
try:
    result = query_tools.query_nearby_attractions(lat, lng, radius)
except Exception as e:
    logger.error(f"查询失败 | error={str(e)}")
    # 返回空结果或抛出异常
    return {"data": []}
```

### 8.2 订单执行错误

```python
# 事务回滚机制
try:
    result = book_restaurant(...)
except Exception as e:
    # 回滚已执行的订单
    await _rollback_orders(executed_orders)
    raise
```

---

## 九、日志记录

### 9.1 工具调用日志

```python
# QueryTools 中的日志
def query_nearby_attractions(self, lat, lng, radius):
    logger.info(f"查询附近景点 | lat={lat} | lng={lng} | radius={radius}")
    result = get_nearby_attractions(lat, lng, radius)
    logger.info(f"查询完成 | count={len(result.get('data', []))}")
    return result
```

### 9.2 执行日志

```python
# ExecuteTools 中的日志
def book_restaurant(self, restaurant_id, date, time, people):
    logger.info(f"预订餐厅 | restaurant_id={restaurant_id} | date={date} | time={time} | people={people}")
    result = book_restaurant(restaurant_id, date, time, people)
    if result.get("code") == 0:
        logger.info(f"预订成功 | booking_id={result['data']['booking_id']}")
    return result
```