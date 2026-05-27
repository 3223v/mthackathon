# 情侣/个人出行规划 Skill

## 触发条件
当用户表达以下意图时自动触发：
- 和对象/男/女朋友出去玩
- 约会安排
- 个人休闲出行
- 涉及浪漫、文艺氛围的出行需求

## 输入参数
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| scenario | str | 是 | "couple" 或 "solo" |
| duration_hours | int | 否 | 预计出行时长，默认4-6小时 |
| budget_range | str | 否 | 预算范围 |
| preferred_types | list | 否 | 偏好的活动类型 |

## 业务流程
1. **信息确认**：确认是约会还是个人出行、预算、偏好
2. **方案规划**：
   - 约会：推荐浪漫、文艺的景点和餐厅
   - 安排拍照打卡点
   - 考虑交通距离和氛围
3. **方案呈现**：输出完整行程时间线
4. **一键执行**：
   - 门票/活动预约
   - 餐厅预约
   - 可选：鲜花配送

## 能力清单
| 能力 | 工具函数 | 说明 |
|------|---------|------|
| 查询景点 | query_attractions(romantic=True) | 返回适合约会的景点 |
| 查询餐厅 | query_restaurants(romantic=True) | 返回有氛围的餐厅 |
| 查询活动 | query_activities(romantic=True) | 返回适合的活动 |
| 购买门票 | book_ticket(attraction_id, adult_count) | 购买门票 |
| 餐厅预约 | book_restaurant(restaurant_id, time, party_size=2) | 预约餐厅 |
| 活动预约 | book_activity(activity_id, time, participants=2) | 预约活动 |
| 鲜花配送 | order_flower(flower_type, delivery_address, delivery_time) | 送到餐厅 |

## 输出模板
```
📋 约会出行方案

💑 出行信息：2人
🕐 时间：{date} {start_time}-{end_time}
💰 预计花费：{total_budget}元

━━━━━━━━━━━━━━━━━━━━

🕐 {time1} | 📍 {place_name}
   地址：{address}
   推荐理由：{reason}

🍽️ {time2} | 🍴 {restaurant_name}
   地址：{address}
   菜系：{cuisine}
   预计花费：{price}元/人
   氛围：{atmosphere}

🎁 惊喜安排：{surprise}

━━━━━━━━━━━━━━━━━━━━
✅ 已完成操作：
- [x] 门票已购买
- [x] 餐厅已预约
- [x] 鲜花已下单配送

📌 小贴士：
{tips}
```
