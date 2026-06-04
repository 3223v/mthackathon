"""
Top-K 替代方案引擎

为规划方案中的每个活动节点计算 Top-K 替代方案，构建多起点有向无环图（DAG）
以及二维矩阵（横向=节点位置，纵向=原始+替代方案），交通也是独立节点。

输出结构：
{
  "plan_id": "...",
  "nodes": [...],       # 所有节点（原始 + 替代）
  "edges": [...],       # 节点间的交通边
  "recommended_path": [...],  # 推荐路径（主方案）
  "matrix": [...],      # 二维矩阵 [column][row]
  "column_labels": [...], # 每列标签
}

节点ID约定：
- 原始活动: "n{index}"
- 替代方案: "n{index}_alt{k}"
- 交通活动: "t{from_index}_to_{to_index}"
"""

import json
import asyncio
import random
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor
from langchain_core.messages import SystemMessage, HumanMessage
from tools.query_tools import QueryTools
from core.travel import calculate_route, TRANSPORT_MODES
from utils import logger

query_tools = QueryTools()
_executor = ThreadPoolExecutor(max_workers=4)


async def generate_alternatives_graph(
    plan: List[Dict],
    plan_id: str,
    llm_manager,
    top_k: int = 3,
) -> Dict[str, Any]:
    """
    为 plan 中的每个活动生成 Top-K 替代方案

    Args:
        plan: 当前规划方案（含交通活动）
        plan_id: 方案ID
        llm_manager: LLM管理器
        top_k: 每个活动的替代数量

    Returns:
        DAG 图结构
    """
    # 过滤出非交通活动
    activity_nodes = [a for a in plan if a.get("activity_type") != "transport"]
    transport_nodes = [a for a in plan if a.get("activity_type") == "transport"]

    if not activity_nodes:
        return {"plan_id": plan_id, "nodes": [], "edges": [], "recommended_path": []}

    logger.info(f"生成替代方案 | plan_id={plan_id} | activities={len(activity_nodes)} | top_k={top_k}")

    # 并行查询每个活动的替代项
    all_alternatives = []
    for i, activity in enumerate(activity_nodes):
        alts = _query_alternatives_for_activity(activity)
        if alts:
            # 用 LLM 评分排序
            ranked = await _rank_alternatives(activity, alts, plan, i, llm_manager, top_k)
            all_alternatives.append({
                "activity_index": i,
                "original": activity,
                "alternatives": ranked,
            })
        else:
            all_alternatives.append({
                "activity_index": i,
                "original": activity,
                "alternatives": [],
            })

    # 构建 DAG
    dag = _build_dag(activity_nodes, all_alternatives)

    logger.info(f"替代方案生成完成 | plan_id={plan_id} | nodes={len(dag['nodes'])} | edges={len(dag['edges'])}")
    return dag


def _query_alternatives_for_activity(activity: Dict) -> List[Dict]:
    """查询单个活动的替代项"""
    act_type = activity.get("activity_type", "")
    loc = activity.get("location", {})
    lat = loc.get("lat", 39.9042)
    lng = loc.get("lng", 116.4074)
    name = activity.get("name", "")

    query_map = {
        "restaurant": ("query_nearby_restaurants", 5000),
        "attraction": ("query_nearby_attractions", 10000),
        "activity": ("query_nearby_activities", 10000),
        "cafe": ("query_nearby_cafes", 5000),
    }

    func_name, radius = query_map.get(act_type, (None, 5000))
    if not func_name:
        return []

    func = getattr(query_tools, func_name, None)
    if not func:
        return []

    try:
        result = func(lat=lat, lng=lng, radius=radius)
        items = result.get("data", [])
        # 过滤自身
        items = [i for i in items if i.get("name") != name and i.get("id") != activity.get("item_id")]
        return items[:10]
    except Exception as e:
        logger.warning(f"替代查询失败 | activity={name} | error={e}")
        return []


async def _rank_alternatives(
    original: Dict,
    alternatives: List[Dict],
    plan: List[Dict],
    activity_index: int,
    llm_manager,
    top_k: int,
) -> List[Dict]:
    """使用 LLM 对替代项进行适配度评分排序"""
    if len(alternatives) <= top_k:
        # 不超过 top_k，直接返回（附带简单排序）
        sorted_alts = sorted(
            alternatives,
            key=lambda a: (a.get("rating", 0) if isinstance(a.get("rating"), (int, float)) else 0),
            reverse=True,
        )
        return sorted_alts[:top_k]

    # 构建 LLM prompt
    alt_list = "\n".join(
        f"{j}. [{a.get('id', '?')}] {a.get('name', '?')} "
        f"⭐{a.get('rating', '?')} 💰{a.get('price', a.get('price_per_person', '?'))}元 "
        f"标签: {', '.join(a.get('tags', []))} "
        f"适合: {', '.join(a.get('suitable_for', []))}"
        for j, a in enumerate(alternatives)
    )

    prompt = (
        f"原始活动: {original.get('name', '')} (类型: {original.get('activity_type', '')})\n"
        f"评分: {original.get('details', {}).get('rating', '')} | "
        f"价格: {original.get('details', {}).get('price', '')}\n\n"
        f"候选替代项（{len(alternatives)}个）:\n{alt_list}\n\n"
        f"请从候选中选出最合适的 {top_k} 个替代项。按适配度从高到低排序。\n"
        f"只返回序号（逗号分隔），如: 3,7,1"
    )

    try:
        response = await llm_manager.invoke([
            SystemMessage(content="你是活动推荐专家。只返回序号。"),
            HumanMessage(content=prompt),
        ])
        # 解析序号
        import re
        indices = [int(x) for x in re.findall(r'\d+', response) if 0 <= int(x) < len(alternatives)]
        ranked = [alternatives[i] for i in indices[:top_k]]
        if len(ranked) < top_k:
            # 补充未选中的
            remaining = [a for i, a in enumerate(alternatives) if i not in indices]
            ranked.extend(remaining[:top_k - len(ranked)])
        return ranked[:top_k]
    except Exception as e:
        logger.warning(f"LLM替代排序失败 | error={e}")
        return alternatives[:top_k]


def _build_dag(activity_nodes: List[Dict], all_alternatives: List[Dict]) -> Dict:
    """
    构建 DAG 结构

    节点类型：
    - n{i}: 原始活动
    - n{i}_alt{k}: 替代活动
    - t{a}_to_{b}: 交通边
    """
    nodes = []
    edges = []
    recommended_path = []

    for entry in all_alternatives:
        idx = entry["activity_index"]
        original = entry["original"]
        alternatives = entry["alternatives"]

        # 原始节点
        node_id = f"n{idx}"
        nodes.append({
            "id": node_id,
            "type": "activity",
            "activity_index": idx,
            "is_original": True,
            "activity": original,
        })
        recommended_path.append(node_id)

        # 替代节点
        for k, alt in enumerate(alternatives):
            alt_id = f"n{idx}_alt{k}"
            alt_activity = _build_alternative_activity(original, alt)
            nodes.append({
                "id": alt_id,
                "type": "alternative",
                "activity_index": idx,
                "alternative_index": k,
                "is_original": False,
                "activity": alt_activity,
                "llm_score": k,  # 排名即分数（0最高）
            })

        # 交通边：从前一个节点（原始或替代）到当前节点的所有替代
        if idx > 0:
            prev_entry = all_alternatives[idx - 1]
            prev_original = prev_entry["original"]
            prev_alts = prev_entry["alternatives"]

            # 前驱节点列表
            prev_nodes = [f"n{idx-1}"] + [f"n{idx-1}_alt{k}" for k in range(len(prev_alts))]
            curr_nodes = [f"n{idx}"] + [f"n{idx}_alt{k}" for k in range(len(alternatives))]

            for pn in prev_nodes:
                for cn in curr_nodes:
                    # 获取坐标
                    pn_activity = _get_node_activity(pn, all_alternatives)
                    cn_activity = _get_node_activity(cn, all_alternatives)
                    if pn_activity and cn_activity:
                        route = _calc_edge(pn_activity, cn_activity)
                        if route:
                            edges.append({
                                "from": pn,
                                "to": cn,
                                "transport": route,
                            })

    return {
        "plan_id": "",
        "nodes": nodes,
        "edges": edges,
        "recommended_path": recommended_path,
    }


def _build_alternative_activity(original: Dict, alternative: Dict) -> Dict:
    """从原始活动和替代数据构建替代活动对象"""
    loc = alternative.get("location", {})
    return {
        "name": alternative.get("name", ""),
        "item_id": alternative.get("id", ""),
        "activity_type": original.get("activity_type", ""),
        "location": {
            "lat": loc.get("lat", 0),
            "lng": loc.get("lng", 0),
            "address": alternative.get("address", ""),
        },
        "duration_hours": alternative.get("duration_hours", alternative.get("visit_duration_hours", original.get("duration_hours", 1))),
        "details": {
            "rating": alternative.get("rating", ""),
            "price": alternative.get("price", alternative.get("price_per_person", "")),
            "tags": alternative.get("tags", []),
            "description": f"替代「{original.get('name', '')}」",
        },
        "pre_book": {"need": alternative.get("need_ticket", alternative.get("need_booking", False))},
    }


def _get_node_activity(node_id: str, all_alternatives: List[Dict]) -> Optional[Dict]:
    """根据节点ID获取活动对象"""
    parts = node_id.split("_alt")
    idx = int(parts[0][1:])  # "n0" → 0
    if len(parts) == 1:
        # 原始节点
        for entry in all_alternatives:
            if entry["activity_index"] == idx:
                return entry["original"]
    else:
        # 替代节点
        k = int(parts[1])
        for entry in all_alternatives:
            if entry["activity_index"] == idx:
                alts = entry["alternatives"]
                if k < len(alts):
                    return _build_alternative_activity(entry["original"], alts[k])
    return None


def _calc_edge(from_activity: Dict, to_activity: Dict) -> Optional[Dict]:
    """计算两个活动之间的交通边"""
    fl = from_activity.get("location", {})
    tl = to_activity.get("location", {})
    if not fl or not tl:
        return None
    try:
        route = calculate_route(
            fl.get("lat", 0), fl.get("lng", 0),
            tl.get("lat", 0), tl.get("lng", 0),
        )
        return {
            "mode": route["mode"],
            "mode_label": route["mode_label"],
            "mode_icon": route["mode_icon"],
            "duration_minutes": route["duration_minutes"],
            "distance_m": route["distance_m"],
        }
    except Exception:
        return None


# ==================== 二维矩阵生成 ====================

async def generate_plan_matrix(
    plan: List[Dict],
    plan_id: str,
    llm_manager,
    top_k: int = 3,
) -> Dict[str, Any]:
    """
    生成二维矩阵结构，将 plan 中的每个位置（包括交通）作为一列，
    纵向为原始方案 + 替代方案。

    矩阵结构:
    {
      "plan_id": "...",
      "matrix": [
        [node_col0_original, node_col0_alt1, node_col0_alt2, ...],  # 第0列
        [node_col1_original, node_col1_alt1, ...],                   # 第1列（可能是交通）
        ...
      ],
      "column_labels": ["活动: 故宫", "交通: 打车→海底捞", "活动: 海底捞", ...],
      "column_types": ["activity", "transport", "activity", ...],
    }

    每个节点对象:
    {
      "id": "n0" / "n0_alt1" / "t0_alt1",
      "label": "故宫" / "打车22分钟" / ...,
      "is_original": true/false,
      "activity": {...},        # 完整的活动对象（含坐标、时间等）
      "transport_info": {...},  # 仅交通节点有
    }
    """
    if not plan:
        return {
            "plan_id": plan_id,
            "matrix": [],
            "column_labels": [],
            "column_types": [],
        }

    logger.info(f"生成矩阵 | plan_id={plan_id} | total_positions={len(plan)} | top_k={top_k}")

    matrix = []
    column_labels = []
    column_types = []

    for col_idx, node in enumerate(plan):
        act_type = node.get("activity_type", "")
        is_transport = (act_type == "transport")

        if is_transport:
            # 交通节点：生成替代交通方式
            column = _build_transport_column(node, col_idx, top_k)
            column_types.append("transport")
            column_labels.append(f"交通: {node.get('name', f'第{col_idx}段')}")
        else:
            # 活动节点：查询替代活动
            column = await _build_activity_column(node, col_idx, llm_manager, top_k)
            column_types.append("activity")
            column_labels.append(f"{act_type}: {node.get('name', f'活动{col_idx}')}")

        matrix.append(column)

    logger.info(f"矩阵生成完成 | plan_id={plan_id} | columns={len(matrix)} | "
                f"transport_cols={column_types.count('transport')} | activity_cols={column_types.count('activity')}")

    return {
        "plan_id": plan_id,
        "matrix": matrix,
        "column_labels": column_labels,
        "column_types": column_types,
    }


def _build_transport_column(node: Dict, col_idx: int, top_k: int) -> List[Dict]:
    """
    为交通节点构建替代列（原始 + 替代交通方式）

    替代方案是不同交通方式（步行/公交/打车/自驾）
    """
    from_loc = node.get("from_location", {})
    to_loc = node.get("to_location", {})
    duration = node.get("duration_minutes", 0)
    distance = node.get("distance_m", 0)

    column = []

    # 原始交通节点
    column.append({
        "id": f"t{col_idx}",
        "label": f"{node.get('mode_label', '')} {duration}分钟",
        "is_original": True,
        "activity": node,
        "transport_info": {
            "mode": node.get("mode", ""),
            "mode_label": node.get("mode_label", ""),
            "mode_icon": node.get("mode_icon", ""),
            "duration_minutes": duration,
            "distance_m": distance,
        },
    })

    # 替代交通方式
    if from_loc and to_loc and distance > 0:
        alt_added = 0
        for mode_key, mode_info in TRANSPORT_MODES.items():
            if alt_added >= top_k:
                break
            if mode_key == node.get("mode", ""):
                continue  # 跳过原始方式

            try:
                route = calculate_route(
                    from_loc.get("lat", 0), from_loc.get("lng", 0),
                    to_loc.get("lat", 0), to_loc.get("lng", 0),
                    mode=mode_key,
                )
                alt_transport = {
                    **node,
                    "mode": route["mode"],
                    "mode_label": route["mode_label"],
                    "mode_icon": route["mode_icon"],
                    "duration_minutes": route["duration_minutes"],
                    "distance_m": route["distance_m"],
                    "name": f"{route['mode_label']}前往{node.get('to_location', {}).get('name', '下一站')}",
                    "details": {
                        "description": f"{route['mode_label']}{route['duration_minutes']}分钟 ({route['distance_m']:.0f}m)",
                    },
                }
                column.append({
                    "id": f"t{col_idx}_alt{alt_added}",
                    "label": f"{route['mode_label']} {route['duration_minutes']}分钟",
                    "is_original": False,
                    "activity": alt_transport,
                    "transport_info": {
                        "mode": route["mode"],
                        "mode_label": route["mode_label"],
                        "mode_icon": route["mode_icon"],
                        "duration_minutes": route["duration_minutes"],
                        "distance_m": route["distance_m"],
                    },
                })
                alt_added += 1
            except Exception as e:
                logger.debug(f"交通替代计算失败 | mode={mode_key} | error={e}")

    return column


async def _build_activity_column(
    node: Dict,
    col_idx: int,
    llm_manager,
    top_k: int,
) -> List[Dict]:
    """为活动节点构建替代列（原始 + LLM排序后的替代方案）"""
    column = []

    # 原始活动节点
    column.append({
        "id": f"n{col_idx}",
        "label": node.get("name", f"活动{col_idx}"),
        "is_original": True,
        "activity": node,
    })

    # 查询替代方案
    act_type = node.get("activity_type", "")
    loc = node.get("location", {})
    lat = loc.get("lat", 39.9042)
    lng = loc.get("lng", 116.4074)
    name = node.get("name", "")
    item_id = node.get("item_id", "")

    query_map = {
        "restaurant": ("query_nearby_restaurants", 5000),
        "attraction": ("query_nearby_attractions", 10000),
        "activity": ("query_nearby_activities", 10000),
        "cafe": ("query_nearby_cafes", 5000),
    }

    func_name, radius = query_map.get(act_type, (None, 5000))
    if not func_name:
        return column

    func = getattr(query_tools, func_name, None)
    if not func:
        return column

    try:
        result = func(lat=lat, lng=lng, radius=radius)
        items = result.get("data", [])
        items = [i for i in items if i.get("name") != name and i.get("id") != item_id]

        if items:
            # LLM 排序
            ranked = await _rank_alternatives_for_matrix(node, items, llm_manager, top_k)
            for k, item in enumerate(ranked[:top_k]):
                alt_activity = _build_alternative_activity(node, item)
                column.append({
                    "id": f"n{col_idx}_alt{k}",
                    "label": item.get("name", f"替代{k+1}"),
                    "is_original": False,
                    "activity": alt_activity,
                    "llm_score": k,
                })
    except Exception as e:
        logger.warning(f"活动替代查询失败 | name={name} | error={e}")

    return column


async def _rank_alternatives_for_matrix(
    original: Dict,
    alternatives: List[Dict],
    llm_manager,
    top_k: int,
) -> List[Dict]:
    """使用 LLM 对替代项评分排序（与 _rank_alternatives 相同逻辑）"""
    if len(alternatives) <= top_k:
        return sorted(
            alternatives,
            key=lambda a: (a.get("rating", 0) if isinstance(a.get("rating"), (int, float)) else 0),
            reverse=True,
        )[:top_k]

    alt_list = "\n".join(
        f"{j}. [{a.get('id', '?')}] {a.get('name', '?')} "
        f"⭐{a.get('rating', '?')} 💰{a.get('price', a.get('price_per_person', '?'))}元 "
        f"标签: {', '.join(a.get('tags', []))}"
        for j, a in enumerate(alternatives)
    )

    prompt = (
        f"原始活动: {original.get('name', '')} (类型: {original.get('activity_type', '')})\n"
        f"评分: {original.get('details', {}).get('rating', '')} | "
        f"价格: {original.get('details', {}).get('price', '')}\n\n"
        f"候选替代项（{len(alternatives)}个）:\n{alt_list}\n\n"
        f"请从候选中选出最合适的 {top_k} 个替代项。按适配度从高到低排序。\n"
        f"只返回序号（逗号分隔），如: 3,7,1"
    )

    try:
        import re
        response = await llm_manager.invoke([
            SystemMessage(content="你是活动推荐专家。只返回序号。"),
            HumanMessage(content=prompt),
        ])
        indices = [int(x) for x in re.findall(r'\d+', response) if 0 <= int(x) < len(alternatives)]
        ranked = [alternatives[i] for i in indices[:top_k]]
        if len(ranked) < top_k:
            remaining = [a for i, a in enumerate(alternatives) if i not in indices]
            ranked.extend(remaining[:top_k - len(ranked)])
        return ranked[:top_k]
    except Exception as e:
        logger.warning(f"LLM替代排序失败 | error={e}")
        return alternatives[:top_k]
