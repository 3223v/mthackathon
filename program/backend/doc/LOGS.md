# 日志系统

## 日志功能说明

后端服务已添加完整的日志系统，记录系统运行、Agent处理、WebSocket通信等关键信息。

## 日志文件

日志文件保存在 `backend/logs/` 目录下，按日期命名：
```
backend/logs/agent_20260101.log
```

## 日志级别

| 级别 | 说明 | 颜色 |
|------|------|------|
| INFO | 重要信息 | 绿色 |
| WARNING | 警告信息 | 黄色 |
| ERROR | 错误信息 | 红色 |
| DEBUG | 调试信息 | 青色 |

## 日志分类

### 1. 系统日志 (agent)
- 系统启动/关闭
- 配置加载
- 数据库初始化

### 2. WebSocket日志 (websocket)
- 连接建立/断开
- 消息收发
- Agent处理状态

### 3. Agent日志 (agent.*)
- 意图分析
- LLM调用
- Skill执行
- 状态更新

### 4. API日志 (api)
- HTTP请求/响应
- 接口调用统计

### 5. Service日志 (service.*)
- 业务逻辑处理
- 数据操作

## 日志示例

### 系统启动
```
2026-01-01 10:00:00 | INFO | agent | ============================================================
2026-01-01 10:00:00 | INFO | agent | 活动规划Agent系统启动中...
2026-01-01 10:00:00 | INFO | agent | ============================================================
2026-01-01 10:00:00 | INFO | agent | 加载配置文件...
2026-01-01 10:00:01 | INFO | agent | 初始化Skill加载器和执行器...
2026-01-01 10:00:01 | INFO | agent | 加载了 3 个Skills
2026-01-01 10:00:01 | INFO | agent | 未检测到OPENAI_API_KEY，将使用模拟模式
```

### WebSocket连接
```
2026-01-01 10:05:00 | INFO | websocket | WebSocket连接已建立 | conversation_id=conv_001
2026-01-01 10:05:00 | INFO | agent | 新建WebSocket连接 | conversation_id=conv_001 | thread_id=xxx-xxx-xxx
```

### 意图分析
```
2026-01-01 10:05:01 | INFO | agent | 分析意图 | conversation_id=conv_001 | input=带孩子出去玩
2026-01-01 10:05:01 | INFO | agent | 通过关键词匹配亲子出行 | skill=Parent-ChildTravelPlanning
2026-01-01 10:05:01 | INFO | agent | 意图分析完成 | conversation_id=conv_001 | skill=Parent-ChildTravelPlanning
```

### Agent响应
```
2026-01-01 10:05:01 | INFO | agent | 使用模拟模式生成响应 | conversation_id=conv_001
2026-01-01 10:05:01 | INFO | agent | 模拟响应生成完成 | length=256
2026-01-01 10:05:01 | INFO | agent | Agent生成响应 | conversation_id=conv_001 | response_length=256
```

### Skill执行
```
2026-01-01 10:05:02 | INFO | agent | 开始执行Skill | conversation_id=conv_001 | skill=Parent-ChildTravelPlanning
2026-01-01 10:05:02 | INFO | agent | Skill执行完成 | conversation_id=conv_001 | plan_id=plan_001
```

### 连接断开
```
2026-01-01 10:10:00 | INFO | websocket | WebSocket连接已关闭 | conversation_id=conv_001
2026-01-01 10:10:00 | INFO | agent | WebSocket连接断开 | conversation_id=conv_001
```

## 查看日志

### 实时查看
```bash
# 在backend目录下运行
cd backend
tail -f logs/agent_20260101.log
```

### 查看最新日志
```bash
tail -n 100 logs/agent_20260101.log
```

### 搜索关键词
```bash
grep "error" logs/agent_20260101.log
grep "conversation_id=conv_001" logs/agent_20260101.log
```

## 日志配置

可以在 `backend/utils/logger.py` 中修改日志配置：

```python
# 日志级别
level: int = logging.INFO

# 日志文件路径
LOG_FILE = os.path.join(LOG_DIR, f"agent_{datetime.now().strftime('%Y%m%d')}.log")
```

## 生产环境建议

1. **日志轮转**: 使用 `logging.handlers.RotatingFileHandler` 防止日志文件过大
2. **日志归档**: 定期压缩旧日志
3. **日志监控**: 配置日志告警，及时发现错误
4. **敏感信息**: 避免在日志中记录密码、API密钥等敏感信息
