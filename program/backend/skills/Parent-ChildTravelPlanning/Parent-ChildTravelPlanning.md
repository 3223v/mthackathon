# 亲子出行规划 Skill

## 触发条件
当用户表达以下意图时自动触发：
- 带孩子/家人出去玩
- 亲子活动、家庭出游
- 周末带娃、遛娃
- 涉及小孩年龄信息的出行需求

## 输入参数
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| child_age | int | 是 | 孩子年龄 |
| group_size | int | 否 | 出行人数，默认3（1大1小）|
| duration_hours | int | 否 | 预计出行时长，默认4-6小时 |
| budget_range | str | 否 | 预算范围，如"500以内" |
| preferred_types | list | 偏好的活动类型 | 如游乐场、博物馆等 |

## 业务流程
1. **信息确认**：确认孩子年龄、出行人数、预算、偏好
2. **方案规划**：
   - 推荐适合孩子年龄的景点/活动
   - 选择有儿童设施的餐厅（儿童椅、儿童餐）
   - 安排合理的活动顺序（先玩后吃 or 先吃后玩）
   - 考虑交通距离和时间
3. **方案呈现**：输出完整的行程时间线
4. **一键执行**：
   - 景点/活动门票购买
   - 餐厅预约（确认有儿童椅）
   - 可选：蛋糕/鲜花配送到餐厅

## 能力清单
| 能力 | 工具函数 | 说明 |
|------|---------|------|
| 查询亲子景点 | query_attractions(family_friendly=True) | 返回适合亲子的景点 |
| 查询亲子餐厅 | query_restaurants(kids_friendly=True) | 返回有儿童设施的餐厅 |
| 查询亲子活动 | query_activities(kids_friendly=True) | 返回适合孩子的活动 |
| 购买门票 | book_ticket(attraction_id, adult_count, child_count) | 购买景点门票 |
| 餐厅预约 | book_restaurant(restaurant_id, time, party_size, kids_chair=True) | 预约餐厅 |
| 活动预约 | book_activity(activity_id, time, participants) | 预约活动 |
| 蛋糕配送 | order_cake(cake_type, delivery_address, delivery_time) | 蛋糕送到指定地址 |
| 鲜花配送 | order_flower(flower_type, delivery_address, delivery_time) | 鲜花送到指定地址 |

## 输出模板
```
📋 亲子出行方案

👨‍👩‍👧 出行信息：{group_size}人，孩子{child_age}岁
🕐 时间：{date} {start_time}-{end_time}
💰 预计花费：{total_budget}元

━━━━━━━━━━━━━━━━━━━━

🕐 {time1} | 📍 {activity_name}
   地址：{address}
   预计游玩：{duration}小时
   门票：{price}元

🍽️ {time2} | 🍴 {restaurant_name}
   地址：{address}
   菜系：{cuisine}
   预计花费：{price}元/人
   推荐菜品：{must_order}

🎁 额外安排：{additional_arrangements}

━━━━━━━━━━━━━━━━━━━━
✅ 已完成操作：
- [x] 景点门票已购买
- [x] 餐厅已预约（已确认儿童椅）
- [x] 蛋糕已下单配送

📌 小贴士：
{tips}
```

## 注意事项
- 孩子年龄≤5岁：优先室内游乐场、低龄友好的景点
- 孩子年龄6-10岁：可加入科普类、手工体验类
- 距离控制在用户偏好范围内
- 餐厅必须有儿童椅和儿童餐选项
- 注意活动时长是否适合孩子体力
