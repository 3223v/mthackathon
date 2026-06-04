# 前端对接指南 v3

---

## 1. WebSocket 连接

```
ws://localhost:8000/ws/chat
```

---

## 2. 消息类型

### 发送

| type | 说明 | payload |
|------|------|---------|
| `message` | 普通消息 | `{"type":"message", "content":"..."}` |
| `interrupt` | 打断/补充 | `{"type":"interrupt", "content":"..."}` |
| `retry` | 手动重试 | `{"type":"retry"}` |
| `retry_planner` | 立即重试规划（跳过倒计时） | `{"type":"retry_planner"}` |

### 接收事件

| type | 说明 |
|------|------|
| `chunk` | LLM 流式 token |
| `plan` | 结构化方案（含交通活动） |
| `plan_updated` | 方案已更新 |
| `plan_validation_failed` | JSON 校验失败，触发倒计时重试（含 `countdown`, `message`） |
| `ai_message` | 展示文本 |
| `skill_detected` | 匹配的技能 |
| `thinking` | 处理进度 |
| `preference_update` | 偏好已更新 |
| `error` | 错误（含 `code`, `retry` 字段） |
| `done` | 本轮完成 |

---

## 3. Plan 结构（v3：交通作为一等公民）

```json
[
  {
    "order": 1,
    "time_slot": {"start": "13:00", "end": "15:00"},
    "activity_type": "attraction",
    "name": "北京动物园",
    "item_id": "AT1004",
    "location": {"lat": 39.942, "lng": 116.343, "address": "西直门外大街137号"},
    "duration_hours": 2,
    "details": {"rating": 4.4, "price": 15, "tags": ["动物","亲子"]},
    "pre_book": {"need": true, "type": "ticket", "item": "成人票x2"},
    "notes": ""
  },
  {
    "order": 2,
    "time_slot": {"start": "15:00", "end": "15:22"},
    "activity_type": "transport",
    "name": "打车前往海底捞火锅",
    "from_location": {"lat": 39.942, "lng": 116.343, "name": "北京动物园"},
    "to_location": {"lat": 39.943, "lng": 116.355, "name": "海底捞火锅"},
    "duration_minutes": 22,
    "distance_m": 10043,
    "mode": "taxi",
    "mode_label": "打车",
    "mode_icon": "🚕",
    "details": {"description": "从「北京动物园」打车22分钟到「海底捞火锅」"}
  },
  {
    "order": 3,
    "time_slot": {"start": "15:30", "end": "17:00"},
    "activity_type": "restaurant",
    "name": "海底捞火锅（西直门店）",
    ...
  }
]
```

**关键变化**: `transport_from_prev` 已移除，交通是独立的 `activity_type: "transport"` 节点。

---

## 4. 重规划操作

### 替换活动
```json
{"type": "message", "content": "换掉海底捞"}
{"type": "message", "content": "第二个不适合，换一个"}
```

### 部分重规划
```json
{"type": "message", "content": "从动物园之后重新规划"}
```

### 全量重规划
```json
{"type": "message", "content": "全部重新规划吧"}
```

---

## 5. Top-K 替代方案（DAG 图）

### 获取替代方案

```http
POST /api/plan/alternatives
Content-Type: application/json

{
  "plan_id": "plan_xxx",
  "plan": [...],    // 完整的 plan 数组
  "top_k": 3
}
```

响应（DAG 结构）：

```json
{
  "plan_id": "plan_xxx",
  "nodes": [
    {
      "id": "n0",
      "type": "activity",
      "activity_index": 0,
      "is_original": true,
      "activity": { "name": "北京动物园", "location": {...}, ... }
    },
    {
      "id": "n0_alt0",
      "type": "alternative",
      "activity_index": 0,
      "alternative_index": 0,
      "is_original": false,
      "activity": { "name": "朝阳公园", "location": {...}, ... },
      "llm_score": 0
    }
  ],
  "edges": [
    {
      "from": "n0",
      "to": "n1",
      "transport": { "mode": "taxi", "duration_minutes": 22, "distance_m": 5000 }
    },
    {
      "from": "n0_alt0",
      "to": "n1",
      "transport": { "mode": "driving", "duration_minutes": 18, "distance_m": 4000 }
    }
  ],
  "recommended_path": ["n0", "n1", "n2"]
}
```

### 用户自定义路径

当用户在 DAG 图中选择了不同的节点组合后：

```http
POST /api/plan/reroute
Content-Type: application/json

{
  "plan_id": "plan_xxx",
  "selected_nodes": ["n0", "n1_alt1", "n2"],
  "all_nodes": [...]    // 从上一步获取的全部节点
}
```

响应返回完整的 `plan`（含交通活动）。

---

## 6. 二维矩阵（路径选择）v3 新增

### 获取矩阵
```http
POST /api/plan/matrix
Content-Type: application/json

{
  "plan_id": "plan_xxx",
  "plan": [...],    // 完整的 plan 数组（含交通节点）
  "top_k": 3
}
```

响应（矩阵结构）：
```json
{
  "plan_id": "plan_xxx",
  "matrix": [
    [{ "id": "n0", "label": "故宫", "is_original": true, "activity": {...} },
     { "id": "n0_alt0", "label": "天坛", "is_original": false, "activity": {...} }],
    [{ "id": "t1", "label": "打车 22分钟", "is_original": true, "activity": {...}, "transport_info": {...} },
     { "id": "t1_alt0", "label": "公交 30分钟", "is_original": false, ... }],
    ...
  ],
  "column_labels": ["活动: 故宫", "交通: 打车→海底捞", ...],
  "column_types": ["activity", "transport", ...]
}
```

每一列代表方案中的一个节点位置（含交通），每列内是原始方案 + 替代方案。

### 提交路径
```http
POST /api/plan/reroute-matrix
Content-Type: application/json

{
  "plan_id": "plan_xxx",
  "selected_ids": ["n0", "t1_alt1", "n2_alt0"],
  "matrix": [...]
}
```

返回根据选中路径生成的完整 plan。

---

## 7. 下单

先验证：
```http
POST /api/orders/validate
{"plan_id":"...", "plan":[...], "user_name":"...", "date":"2026-06-03"}
```

再执行：
```http
POST /api/orders/execute       # 批量（事务式）
POST /api/orders/execute/{i}    # 单独
```

---

## 8. 打断机制

用户随时可以发送 `interrupt` 消息追加信息：

```json
{"type": "interrupt", "content": "预算控制在500以内"}
```

后端将此消息追加到对话历史，重新执行图流程。已有方案会被保留，根据新信息调整。

---

## 9. 错误处理与重试

错误事件格式：
```json
{
  "type": "error",
  "code": "TRANSIENT",
  "message": "处理出错: ...",
  "retry": true,
  "retry_instruction": "发送 {\"type\": \"retry\"} 手动重试"
}
```

前端可以：
- 显示错误信息给用户
- 如果 `retry: true`，提供"重试"按钮
- 发送 `{"type": "retry"}` 让后端重试最后一条消息
