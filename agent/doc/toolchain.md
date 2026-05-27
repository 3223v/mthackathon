# 工具调用链路（Tool Chain）

## 概述

Agent 的工具分为两层：**查询层（query）** 和 **执行层（book）**。

```
┌──────────────────────────────────────────────┐
│                   Agent                       │
│                                               │
│  generate_plan ──→ tools/query.py            │
│                       │                       │
│                   查询 mock 数据               │
│                       │                       │
│                   返回候选列表                 │
│                       │                       │
│  execute_plan ───→ tools/book.py             │
│                       │                       │
│                   生成订单                     │
│                       │                       │
│                   写入 data/orders.json       │
└──────────────────────────────────────────────┘
```

## 查询层（tools/query.py）

所有查询函数都从 `mock/` 目录读取 JSON 数据，支持多维度过滤。

### query_attractions()

查询景点列表。

| 参数 | 类型 | 说明 |
|------|------|------|
| scenario | str | 场景标签过滤（亲子/朋友/情侣） |
| max_distance | float | 最大距离（km） |
| child_age | int | 孩子年龄，用于排除不适合的景点 |
| tags | list | 标签匹配 |

**数据源**：`mock/attractions.json`（8个景点）

### query_restaurants()

查询餐厅列表。

| 参数 | 类型 | 说明 |
|------|------|------|
| scenario | str | 场景标签过滤 |
| max_distance | float | 最大距离 |
| max_budget_per_person | float | 人均预算上限 |
| cuisine | str | 菜系关键词 |
| need_kids_friendly | bool | 是否需要儿童设施 |
| min_capacity | int | 最少容纳人数 |

**数据源**：`mock/restaurants.json`（8家餐厅）

### query_activities()

查询活动列表。

| 参数 | 类型 | 说明 |
|------|------|------|
| scenario | str | 场景标签过滤 |
| max_distance | float | 最大距离 |
| child_age | int | 孩子年龄，过滤年龄限制 |
| tags | list | 标签匹配 |

**数据源**：`mock/activities.json`（10种活动）

### query_cakes() / query_flowers()

查询蛋糕/鲜花，仅按场景过滤。

**数据源**：`mock/cakes_flowers.json`

## 执行层（tools/book.py）

所有执行函数生成订单记录并持久化到 `data/orders.json`。

### book_restaurant()

餐厅预约。

```python
book_restaurant(
    restaurant_id="R001",
    restaurant_name="海底捞火锅",
    date="2026-05-27",
    time="18:00",
    party_size=4,
    need_kids_chair=True,
    special_requests="亲子出行，有5岁孩子"
)
# → {"order_id": "MT10001", "status": "已预约", ...}
```

### book_activity()

活动预约（密室逃脱、手工体验、桌游等）。

```python
book_activity(
    activity_id="ACT002",
    activity_name="密室逃脱「时空穿越」",
    time="14:00",
    participants=4
)
# → {"order_id": "MT10002", "status": "已预约", ...}
```

### book_movie()

电影票购买（特殊活动类型单独处理）。

```python
book_movie(
    movie_name="功夫熊猫5",
    cinema="南山区万象影城",
    showtime="14:30",
    seat_count=3
)
# → {"order_id": "MT10003", "status": "已出票", ...}
```

### order_cake() / order_flower()

蛋糕/鲜花配送到指定地址。

```python
order_cake(
    cake_name="儿童卡通蛋糕（6寸）",
    delivery_address="南山区科技园路",
    delivery_time="18:00",
    message_card="祝大家玩得开心！"
)
# → {"order_id": "MT10004", "status": "已下单", ...}
```

## 完整调用链示例

以"亲子出行"为例：

```
用户: 今天下午带5岁的孩子出去玩

1. analyze_input
   → intent=plan, scenario=family, child_age=5

2. select_skill
   → Parent-ChildTravelPlanning

3. generate_plan
   → query_attractions(scenario="亲子", child_age=5)
   → query_restaurants(scenario="亲子", need_kids_friendly=True)
   → query_activities(scenario="亲子", child_age=5)
   → LLM 从候选中选择并生成 timeline

4. [展示方案，等待确认]

5. 用户: 确认

6. execute_plan
   → book_activity(ACT006, "儿童乐园", "14:00", 3)
   → book_restaurant(R003, "西贝莜面村", "18:00", 3, kids_chair=True)
   → order_cake("儿童卡通蛋糕", "西贝莜面村地址", "18:00")

7. format_result
   → 展示方案 + 订单号汇总
```

## 订单持久化

所有订单写入 `data/orders.json`，格式：

```json
{
  "orders": [
    {
      "order_id": "MT10001",
      "type": "活动预约",
      "activity_name": "亲子DIY蛋糕",
      "date": "2026-05-27",
      "time": "14:00",
      "participants": 3,
      "status": "已预约",
      "created_at": "2026-05-27T13:00:00"
    }
  ],
  "next_id": 10002
}
```
