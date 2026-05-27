# 异常处理机制（Error Handling）

## 概述

Agent 在多个环节可能遇到异常，本文档描述各类异常的处理策略。

## LLM 响应解析异常

### 问题

LLM 返回的内容可能不是严格的 JSON：
- 被包裹在 ` ```json ... ``` ` 代码块中
- 包含多余的解释文字
- JSON 格式错误

### 处理策略

使用 `_parse_llm_json()` 统一处理：

```python
def _parse_llm_json(response_text: str, fallback: dict) -> dict:
    # 1. 尝试提取 ```json ... ``` 代码块
    # 2. 直接 json.loads
    # 3. 失败则返回 fallback 兜底值
```

每个调用 LLM 的节点都有独立的 fallback 值：

| 节点 | fallback 行为 |
|------|--------------|
| analyze_input | 默认 intent=plan, scenario=friends, 继续流程 |
| generate_plan | 返回空方案，提示用户 |
| handle_interrupt | 使用 medium 影响级别，继续重新规划 |
| handle_preference | 默认 action=set，提示已收到 |

## 信息缺失

### 问题

用户输入信息不足以生成方案（如只说"出去玩"没说和谁）。

### 处理策略

- analyze_input 节点通过 LLM 提取 `missing_info` 列表
- 如果 missing_info 非空，路由到 gather_info 节点
- gather_info 最多追问 2 个关键问题
- 追问后节点结束，等待用户下一轮补充

## API 调用失败

### 问题

LLM API 不可达（网络错误、Key 无效、额度不足）。

### 处理策略

当前版本不做自动重试，直接抛出异常。建议：
- 检查 `.env` 中的 API Key 是否正确
- 检查 `config/llm_config.json` 中的 base_url 是否可达
- 确认 API 额度充足

**扩展方向**：可在 `_get_llm()` 中实现多配置 fallback。

## 用户打断

### 问题

用户在方案讨论中突然加入新信息。

### 处理策略

这不是异常，而是正常功能。处理流程：

1. Agent 类检测到当前 step=wait_confirmation 且输入不是确认词
2. 调用 handle_interrupt 节点分析新信息的影响
3. LLM 评估 impact（low/medium/high）
4. 无论影响大小，都重新生成方案
5. 自动从打断信息中提取偏好并持久化

## 方案生成失败

### 问题

LLM 生成的方案 JSON 格式错误或内容为空。

### 处理策略

- `_parse_llm_json()` 返回 fallback 空方案
- Agent 展示时检测 timeline 为空，提示用户重新输入
- 用户可以再次发送相同请求重试

## mock 数据缺失

### 问题

查询工具找不到匹配的数据（如条件太严格）。

### 处理策略

- 查询函数返回空列表
- generate_plan 收到空列表时，LLM 会基于通用知识补充建议
- 如果所有数据源都为空，LLM 仍然可以生成一个建议性的方案

## 状态图循环保护

### 问题

打断 → 重新规划 → 再打断 → 无限循环。

### 处理策略

- `.env` 中 `Max_Step=1000` 限制最大步数
- 每个节点递增 `step_count`
- 超过限制时 Agent 应终止（扩展点）

## 数据写入失败

### 问题

`data/` 目录不存在或无写入权限。

### 处理策略

- `preferences.py` 和 `book.py` 中在写入前自动创建目录
- 使用 `os.makedirs(..., exist_ok=True)`
- 写入失败时抛出 IOError，由调用方处理

## 确认词误判

### 问题

用户说"不行"/"不可以"被误判为确认。

### 处理策略

- `_is_confirmation()` 使用精确匹配列表
- 只匹配明确的确认词（好的、确认、执行等）
- 否定词不在列表中，不会被误判
- 如有误判，用户可以继续打断重新调整
