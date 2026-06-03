# 异常处理机制文档

## 概述

本文档详细描述活动规划 Agent 系统的异常处理机制，包括错误分类、处理策略、重试机制和故障恢复方案。

---

## 一、错误分类体系

### 1.1 错误类型定义

#### 1.1.1 按可恢复性分类

| 类型 | 定义 | 示例 | 是否可重试 |
|------|------|------|------------|
| **Transient（瞬态错误）** | 临时故障，可自动恢复 | 网络超时、LLM 服务不可用、限流 | 是 |
| **Permanent（永久错误）** | 代码逻辑错误或数据错误 | 参数错误、KeyError、TypeError | 否 |

#### 1.1.2 按错误来源分类

| 来源 | 错误类型 | 处理策略 |
|------|----------|----------|
| **LLM 服务** | 超时、服务不可用、限流 | 多 LLM 轮询 + 自动重试 |
| **网络层** | 连接失败、超时 | 自动重试 + 指数退避 |
| **数据层** | 数据不存在、格式错误 | 优雅降级、返回空结果 |
| **业务逻辑** | 约束冲突、状态错误 | 业务提示、用户确认 |
| **系统层** | 资源耗尽、配置错误 | 告警、人工介入 |

### 1.2 错误码规范

#### 1.2.1 错误码结构

```
<来源><子系统><序号>
```

#### 1.2.2 错误码列表

| 错误码 | 描述 | 分类 |
|--------|------|------|
| **LLM001** | LLM 调用超时 | Transient |
| **LLM002** | LLM 服务不可用 | Transient |
| **LLM003** | LLM 响应格式错误 | Permanent |
| **NET001** | 网络连接失败 | Transient |
| **NET002** | 请求超时 | Transient |
| **DTA001** | 数据查询失败 | Transient |
| **DTA002** | 数据格式错误 | Permanent |
| **BUS001** | 活动不存在 | Permanent |
| **BUS002** | 时间冲突 | Business |
| **BUS003** | 预订失败 | Transient |
| **SYS001** | 配置错误 | Permanent |
| **SYS002** | 资源不足 | Transient |

---

## 二、LLM 异常处理

### 2.1 多 LLM 轮询机制

#### 2.1.1 轮询策略

```python
class LLMManager:
    def __init__(self, configs: list):
        self.llms = []
        self.current_index = 0
        self.retry_count = 3
        self.retry_delay = 2
        
    def _get_next_llm(self):
        """获取下一个可用的 LLM"""
        if not self.llms:
            return None, None
        llm_info = self.llms[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.llms)
        return llm_info["llm"], llm_info["config"]
```

#### 2.1.2 自动重试流程

```
调用 LLM
    │
    ├─ 成功 → 返回结果
    │
    └─ 失败
        │
        ├─ 重试次数 < 最大重试次数
        │   ├─ 等待 (retry_delay * 1.5^attempt)
        │   └─ 切换到下一个 LLM，重试
        │
        └─ 重试次数 >= 最大重试次数 → 抛出异常
```

#### 2.1.3 指数退避策略

| 重试次数 | 等待时间 |
|----------|----------|
| 1 | 2s |
| 2 | 3s |
| 3 | 4.5s |

### 2.2 LLM 响应解析错误处理

#### 2.2.1 JSON 解析失败

```python
def _parse_plan_json(text: str) -> List[Dict]:
    """从 LLM 输出中解析 plan JSON"""
    # 尝试从 markdown 代码块提取
    code_match = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
    if code_match:
        text = code_match.group(1).strip()
    
    try:
        plan = json.loads(text)
        if isinstance(plan, list):
            return plan
    except json.JSONDecodeError:
        pass
    
    # 尝试直接匹配数组
    array_match = re.search(r'\[.*\]', text, re.DOTALL)
    if array_match:
        try:
            plan = json.loads(array_match.group(0))
            if isinstance(plan, list):
                return plan
        except json.JSONDecodeError:
            pass
    
    logger.warning(f"无法解析 plan JSON | preview={text[:200]}")
    return []
```

#### 2.2.2 解析失败降级策略

```python
async def generate_plan(state: AgentState, llm_manager, stream_callback):
    try:
        response_text = await llm_manager.invoke_with_logging(...)
        
        plan = _parse_plan_json(response_text)
        if not plan:
            # 解析失败，返回原始文本作为回复
            logger.warning(f"JSON解析失败，返回原始文本")
            return {
                "messages": [AIMessage(content=response_text)],
                "plan": [],
                "plan_id": "",
            }
        
        # 继续正常处理...
        plan = _insert_transport_activities(plan)
        return {"plan": plan, "plan_id": plan_id, "messages": [...]}
    
    except Exception as e:
        logger.error(f"规划生成失败 | error={str(e)}")
        return {
            "messages": [AIMessage(content=f"抱歉，规划生成失败：{str(e)}")],
            "plan": [],
            "plan_id": "",
        }
```

---

## 三、WebSocket 异常处理

### 3.1 错误分类函数

```python
def _classify_error(error: Exception) -> str:
    """分类错误类型"""
    error_str = str(error).lower()
    error_type = type(error).__name__
    
    # 可重试的错误模式
    transient_patterns = [
        "timeout", "timed out", "connection", "rate limit",
        "too many requests", "server error", "5xx", "503",
        "overloaded", "capacity", "unavailable", "try again",
    ]
    for pat in transient_patterns:
        if pat in error_str or pat in error_type.lower():
            return "transient"
    
    # 永久错误类型
    if isinstance(error, (TypeError, ValueError, KeyError, AttributeError, IndexError)):
        return "permanent"
    
    return "permanent"
```

### 3.2 自动重试机制

```python
# WebSocket 消息处理循环
max_auto_retries = 2
retry_count = 0

while retry_count <= max_auto_retries:
    try:
        async for event in graph.astream(state, config):
            # 处理节点事件...
            pass
        
        await websocket.send_json({"type": "done", ...})
        break  # 成功，退出重试循环
    
    except Exception as e:
        error_type = _classify_error(e)
        
        if error_type == "transient" and retry_count < max_auto_retries:
            retry_count += 1
            wait_s = retry_count * 2
            
            await websocket.send_json({
                "type": "error",
                "code": "AUTO_RETRY",
                "message": f"处理遇到问题，正在自动重试 ({retry_count}/{max_auto_retries})...",
                "retry": True,
                "retry_count": retry_count,
            })
            
            await asyncio.sleep(wait_s)
        
        else:
            # 永久错误或重试耗尽
            await websocket.send_json({
                "type": "error",
                "code": error_type.upper(),
                "message": f"处理出错: {error_str[:200]}",
                "retry": True,
                "retry_instruction": "发送 {\"type\": \"retry\"} 手动重试",
            })
```

### 3.3 前端重试支持

#### 3.3.1 手动重试消息

```json
{"type": "retry"}
```

#### 3.3.2 重试处理逻辑

```python
if message_type == "retry":
    if last_user_message:
        content = last_user_message
        message_type = "message"
        await websocket.send_json({"type": "status", "content": "正在重试..."})
    else:
        await websocket.send_json({
            "type": "error", 
            "code": "RETRY_NO_MESSAGE", 
            "message": "没有可重试的消息", 
            "retry": False
        })
        continue
```

---

## 四、事务下单异常处理

### 4.1 事务保证机制

#### 4.1.1 三阶段执行流程

```
阶段1: 收集待下单项
    │
    ├─ 遍历 plan 中所有 pre_book.need=True 的活动
    └─ 构建待下单列表
    
阶段2: 验证可用性
    │
    ├─ 调用 check_restaurant_availability()
    ├─ 调用 check_activity_availability()
    └─ 任一失败 → 返回失败，不执行任何订单
    
阶段3: 执行订单
    │
    ├─ 依次调用 book_restaurant()/book_ticket()/order_delivery()
    └─ 任一失败 → 回滚已执行订单
```

#### 4.1.2 回滚机制

```python
async def execute_all_orders(payload: PlanForOrder):
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
            # 回滚已执行的订单
            logger.error(f"下单失败 | error={str(e)}")
            await _rollback_orders(order_results)
            
            return {
                "success": False,
                "message": f"「{order_info['name']}」下单失败，已回滚所有订单。错误: {str(e)}",
                "failed_at_index": order_info["index"],
                "orders": order_results,
            }
    
    return {"success": True, "orders": order_results}
```

### 4.2 订单验证错误处理

```python
@app.post("/api/orders/validate")
async def validate_orders(payload: PlanForOrder):
    results = []
    all_valid = True
    
    for i, activity in enumerate(payload.plan):
        pre_book = activity.get("pre_book", {})
        if not pre_book or not pre_book.get("need"):
            continue
        
        validation = {
            "order_index": i,
            "activity_name": activity.get("name", "未知"),
            "order_type": activity.get("activity_type", ""),
            "valid": True,
            "message": "",
        }
        
        try:
            if act_type == "restaurant":
                avail = check_restaurant_availability(...)
                if not avail.get("data", {}).get("available", False):
                    validation["valid"] = False
                    validation["message"] = f"餐厅不可用: {avail_data.get('estimated_wait', '需等位')}"
                else:
                    validation["message"] = f"可用（{avail_data.get('available_seats', 0)}座）"
                    
        except Exception as e:
            validation["valid"] = False
            validation["message"] = f"验证异常: {str(e)}"
            logger.error(f"验证失败 | activity={name} | error={str(e)}")
        
        if not validation["valid"]:
            all_valid = False
        results.append(validation)
    
    return {"plan_id": payload.plan_id, "all_valid": all_valid, "results": results}
```

---

## 五、业务异常处理

### 5.1 重规划异常处理

#### 5.1.1 目标活动定位失败

```python
def _not_found_response(target_desc: str):
    return {"messages": [AIMessage(
        content=f"未找到「{target_desc}」。请用序号（如\"换掉第一个\"）或名称来指定。"
    )]}

async def replace_activity(state: AgentState, llm_manager, stream_callback):
    target_index = _find_target_activity(plan, replan_target)
    
    # LLM 兜底
    if target_index is None and replan_target.get("target_description"):
        target_index = await _llm_find_target(...)
    
    if target_index is None:
        logger.warning(f"无法定位目标活动 | target={replan_target}")
        return _not_found_response(replan_target.get("target_description", "该活动"))
```

#### 5.1.2 无替代方案

```python
def _no_alternatives_response(name: str):
    return {"messages": [AIMessage(
        content=f"附近没有找到「{name}」的合适替代，请尝试扩大范围或换一种类型。"
    )]}

async def replace_activity(...):
    alternatives = _query_alternatives(target_activity, constraints, query_results)
    
    if not alternatives:
        return _no_alternatives_response(target_activity.get("name", "该活动"))
```

#### 5.1.3 无现有规划

```python
def _no_plan_response():
    return {"messages": [AIMessage(
        content="当前还没有规划方案，请先告诉我你的出行需求。"
    )]}

async def partial_replan(state: AgentState, llm_manager, stream_callback):
    plan = state.get("plan", [])
    
    if not plan:
        return _no_plan_response()
```

### 5.2 数据查询异常处理

```python
class QueryTools:
    def query_by_filters(self, lat, lng, filters=None):
        try:
            # 执行查询
            result = {}
            
            attr_result = get_nearby_attractions(lat, lng, 20000, ...)
            result["attractions"] = attr_result.get("data", [])
            
            # ... 其他查询
            
            return result
            
        except Exception as e:
            logger.error(f"查询失败 | error={str(e)}")
            # 返回空结果，允许系统继续运行
            return {
                "attractions": [],
                "restaurants": [],
                "activities": [],
                "cafes": [],
            }
```

---

## 六、错误日志与监控

### 6.1 日志记录规范

#### 6.1.1 错误日志格式

```python
logger.error(f"[节点: planner] 规划生成失败 | cid={conversation_id} | error={str(e)}")
```

#### 6.1.2 日志级别使用

| 级别 | 使用场景 |
|------|----------|
| **DEBUG** | 详细调试信息，仅开发环境 |
| **INFO** | 正常业务流程记录 |
| **WARNING** | 潜在问题、降级处理 |
| **ERROR** | 错误发生，影响功能 |
| **CRITICAL** | 严重错误，系统可能无法继续 |

### 6.2 日志输出示例

```
2024-01-15 10:30:45 | ERROR | agent | [WS] Agent错误 | cid=conv_abc123 | type=transient | timeout
2024-01-15 10:30:48 | INFO | agent | [WS] 自动重试 | cid=conv_abc123 | attempt=1/2 | wait=2s
2024-01-15 10:30:51 | INFO | agent | [节点: planner] 规划完成 | cid=conv_abc123 | plan_id=plan_xyz789 | items=5
```

### 6.3 监控指标

| 指标 | 说明 | 监控方式 |
|------|------|----------|
| **LLM 调用成功率** | LLM 调用成功次数/总次数 | 日志统计 |
| **平均响应时间** | 每次请求的平均处理时间 | 日志统计 |
| **错误率** | 错误请求数/总请求数 | 日志统计 |
| **重试次数** | 自动重试的总次数 | 日志统计 |
| **订单成功率** | 订单成功次数/总订单数 | API 统计 |

---

## 七、前端错误处理

### 7.1 错误消息格式

```json
{
    "type": "error",
    "code": "TRANSIENT",
    "message": "处理出错: LLM服务暂时不可用",
    "retry": true,
    "retry_instruction": "发送 {\"type\": \"retry\"} 手动重试"
}
```

### 7.2 错误处理建议

| 错误码 | 前端处理 |
|--------|----------|
| `TRANSIENT` | 显示重试按钮 |
| `PERMANENT` | 显示错误详情，建议用户检查输入 |
| `AUTO_RETRY` | 显示自动重试进度 |
| `RETRY_NO_MESSAGE` | 提示用户重新发送消息 |

---

## 八、故障恢复策略

### 8.1 服务降级

当 LLM 服务全部不可用时：

```python
async def node_planner(state: AgentState, config: RunnableConfig):
    if not llm_manager.has_llms():
        return {"messages": [AIMessage(content="抱歉，当前没有可用的 LLM 服务。")]}
    
    # 正常处理流程...
```

### 8.2 数据降级

当数据源不可用时：

```python
async def query_data(state: AgentState):
    try:
        results = query_tools.query_by_filters(...)
    except Exception as e:
        logger.error(f"数据查询失败 | error={str(e)}")
        results = {"attractions": [], "restaurants": [], ...}
    
    # 使用缓存或默认数据
    if not results["attractions"]:
        results["attractions"] = _get_default_attractions()
    
    return {"query_results": results}
```

### 8.3 状态恢复

WebSocket 连接断开后，会话状态通过 `MemorySaver` 持久化：

```python
# graph.py
checkpointer = MemorySaver()
compiled_graph = workflow.compile(checkpointer=checkpointer)
```

---

## 九、边界情况处理

### 9.1 空数据处理

```python
# planner.py
available_data = format_data_for_prompt(query_results)
if not available_data.strip():
    available_data = "（暂无可用数据，请基于常识推荐北京地区热门景点和餐厅）"
```

### 9.2 时间冲突检测

```python
def _validate_time_slots(plan: List[Dict]) -> bool:
    """验证时间安排是否有冲突"""
    for i in range(len(plan) - 1):
        current_end = plan[i].get("time_slot", {}).get("end", "")
        next_start = plan[i+1].get("time_slot", {}).get("start", "")
        
        if current_end and next_start:
            # 简单比较时间字符串
            if current_end > next_start:
                logger.warning(f"时间冲突: {plan[i]['name']} -> {plan[i+1]['name']}")
                return False
    return True
```

### 9.3 资源耗尽保护

```python
# 限制单次请求处理的最大活动数
MAX_ACTIVITIES_PER_PLAN = 10

async def generate_plan(...):
    plan = _parse_plan_json(response_text)
    
    if len(plan) > MAX_ACTIVITIES_PER_PLAN:
        plan = plan[:MAX_ACTIVITIES_PER_PLAN]
        logger.warning(f"方案活动数超出限制，已截断到 {MAX_ACTIVITIES_PER_PLAN} 个")
    
    # 继续处理...
```