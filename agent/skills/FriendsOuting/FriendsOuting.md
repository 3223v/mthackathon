# 朋友出行规划 Skill

## 触发条件
当用户表达以下意图时自动触发：
- 和朋友出去玩
- 多人出行、聚会
- 涉及男女生组合的出行需求
- 团建、聚餐

## 输入参数
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| group_size | int | 是 | 出行人数 |
| gender_mix | str | 否 | 性别组合，如"2男2女" |
| duration_hours | int | 否 | 预计出行时长，默认4-6小时 |
| budget_range | str | 否 | 人均预算范围 |
| preferred_types | list | 否 | 偏好的活动类型 |

## 业务流程
1. **信息确认**：确认人数、性别比例、预算、偏好
2. **方案规划**：
   - 推荐适合多人参与的活动（密室逃脱、剧本杀、桌游等）
   - 选择适合聚餐的餐厅（大桌、包间）
   - 安排活动顺序，考虑男女兴趣平衡
   - 考虑交通便利性
3. **方案呈现**：输出完整的行程时间线
4. **一键执行**：
   - 活动/门票预约
   - 餐厅预约（确认大桌/包间）
   - 可选：订花/订蛋糕

## 能力清单
| 能力 | 工具函数 | 说明 |
|------|---------|------|
| 查询景点 | query_attractions(group_friendly=True) | 返回适合多人的景点 |
| 查询餐厅 | query_restaurants(group_friendly=True) | 返回适合聚餐的餐厅 |
| 查询活动 | query_activities(group_friendly=True) | 返回适合多人的活动 |
| 购买门票 | book_ticket(attraction_id, adult_count) | 购买景点门票 |
| 餐厅预约 | book_restaurant(restaurant_id, time, party_size) | 预约餐厅 |
| 活动预约 | book_activity(activity_id, time, participants) | 预约活动 |
| 蛋糕配送 | order_cake(cake_type, delivery_address, delivery_time) | 蛋糕送到指定地址 |
| 鲜花配送 | order_flower(flower_type, delivery_address, delivery_time) | 鲜花送到指定地址 |

## 输出模板
```
📋 朋友出行方案

👥 出行信息：{group_size}人（{gender_mix}）
🕐 时间：{date} {start_time}-{end_time}
💰 预计人均花费：{budget_per_person}元

━━━━━━━━━━━━━━━━━━━━

🕐 {time1} | 🎯 {activity_name}
   地址：{address}
   预计时长：{duration}分钟
   费用：{price}元/人
   推荐理由：{reason}

🍽️ {time2} | 🍴 {restaurant_name}
   地址：{address}
   菜系：{cuisine}
   预计花费：{price}元/人
   推荐菜品：{must_order}

🕐 {time3} | 🎯 {activity_name_2}
   地址：{address}
   预计时长：{duration}分钟
   费用：{price}元/人

━━━━━━━━━━━━━━━━━━━━
✅ 已完成操作：
- [x] 活动已预约
- [x] 餐厅已预约

📌 小贴士：
{tips}
```

## 注意事项
- 男女混合出行：平衡活动选择，避免过于偏向某一性别
- 4人组：密室逃脱、剧本杀是最佳选择
- 注意餐厅是否能容纳大桌，是否需要包间
- 人均预算要合理控制
