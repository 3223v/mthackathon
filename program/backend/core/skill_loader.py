"""
Skill 加载器

功能：
1. 加载 skills.json 索引
2. 解析 skills/*.md 的 Markdown 结构
3. 按触发关键词匹配用户意图
4. 返回结构化的 Skill 对象

Skill 对象结构：
{
    "id": str,              # Skill ID
    "name": str,            # 中文名称
    "scenario": str,        # 场景类型 family/friends/couple
    "description": str,     # 简要描述
    "raw_content": str,     # 原始 Markdown 内容
    "triggers": str,        # 触发条件（原始文本）
    "params": list,         # 输入参数列表
    "flow": str,            # 业务流程
    "capabilities": list,   # 能力清单 [{ability, function, description}]
    "output_template": str, # 输出模板
    "notes": str,           # 注意事项
}
"""

import json
import os
import re
from typing import Dict, List, Optional
from utils import logger


# ==================== 路径配置 ====================
CONFIG_DIR = os.path.join(os.path.dirname(__file__), "../config")
SKILLS_INDEX_PATH = os.path.join(CONFIG_DIR, "skills.json")
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")


class SkillLoader:
    """Skill 加载器：加载、解析、匹配 Skill 文件"""

    def __init__(self):
        self.skills_index: List[Dict] = []
        self.skills: Dict[str, Dict] = {}  # id -> parsed skill
        self._loaded = False

    def load_all(self) -> List[Dict]:
        """加载并解析所有 Skill，返回 skill 列表"""
        if self._loaded:
            return list(self.skills.values())

        logger.info("开始加载 Skills...")

        # 1. 加载索引
        try:
            with open(SKILLS_INDEX_PATH, "r", encoding="utf-8") as f:
                self.skills_index = json.load(f)
            logger.info(f"Skill 索引加载成功 | count={len(self.skills_index)}")
        except FileNotFoundError:
            logger.error(f"Skill 索引文件不存在: {SKILLS_INDEX_PATH}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Skill 索引 JSON 解析失败: {e}")
            return []

        # 2. 逐个解析 Skill 文件
        for idx, skill_entry in enumerate(self.skills_index):
            skill_id = skill_entry["id"]
            skill_file = os.path.join(PROJECT_ROOT, skill_entry["skill_file"])

            try:
                parsed = self._parse_skill_md(skill_file)
                if parsed:
                    # 合并索引信息和解析内容
                    skill_obj = {
                        "id": skill_id,
                        "name": skill_entry.get("name", skill_id),
                        "scenario": skill_entry.get("scenario", ""),
                        "description": skill_entry.get("description", ""),
                        "trigger_keywords": skill_entry.get("trigger_keywords", []),
                        "trigger_scenarios": skill_entry.get("trigger_scenarios", []),
                        **parsed,
                    }
                    self.skills[skill_id] = skill_obj
                    logger.info(f"Skill [{skill_id}] 加载成功 | name={skill_obj['name']}")
                else:
                    logger.warning(f"Skill [{skill_id}] 解析结果为空")
            except FileNotFoundError:
                logger.warning(f"Skill 文件未找到: {skill_file}")
            except Exception as e:
                logger.error(f"Skill [{skill_id}] 解析失败: {e}")

        self._loaded = True
        logger.info(f"Skills 加载完成 | loaded={len(self.skills)}/{len(self.skills_index)}")
        return list(self.skills.values())

    def _parse_skill_md(self, filepath: str) -> Optional[Dict]:
        """解析单个 Skill Markdown 文件为结构化数据"""
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        result = {
            "raw_content": content,
            "triggers": "",
            "params": [],
            "flow": "",
            "capabilities": [],
            "output_template": "",
            "notes": "",
        }

        # 解析触发条件
        trigger_match = re.search(
            r'##\s*触发条件\s*\n(.*?)(?=\n##|\n#|\Z)',
            content, re.DOTALL
        )
        if trigger_match:
            result["triggers"] = trigger_match.group(1).strip()

        # 解析输入参数（表格）
        params_match = re.search(
            r'##\s*输入参数\s*\n(.*?)(?=\n##\s|\n#\s|\Z)',
            content, re.DOTALL
        )
        if params_match:
            params_text = params_match.group(1).strip()
            result["params"] = self._parse_params_table(params_text)

        # 解析业务流程
        flow_match = re.search(
            r'##\s*业务流程\s*\n(.*?)(?=\n##\s|\n#\s|\Z)',
            content, re.DOTALL
        )
        if flow_match:
            result["flow"] = flow_match.group(1).strip()

        # 解析能力清单（表格）
        capabilities_match = re.search(
            r'##\s*能力清单\s*\n(.*?)(?=\n##\s|\n#\s|\Z)',
            content, re.DOTALL
        )
        if capabilities_match:
            cap_text = capabilities_match.group(1).strip()
            result["capabilities"] = self._parse_capabilities_table(cap_text)

        # 解析输出模板
        output_match = re.search(
            r'##\s*输出模板\s*\n(.*?)(?=\n##\s|\n#\s|\Z)',
            content, re.DOTALL
        )
        if output_match:
            # 提取代码块中的内容
            template_text = output_match.group(1).strip()
            code_match = re.search(r'```\n(.*?)```', template_text, re.DOTALL)
            if code_match:
                result["output_template"] = code_match.group(1).strip()
            else:
                result["output_template"] = template_text

        # 解析注意事项
        notes_match = re.search(
            r'##\s*注意事项\s*\n(.*?)(?=\n##|\n#|\Z)',
            content, re.DOTALL
        )
        if notes_match:
            result["notes"] = notes_match.group(1).strip()

        return result

    def _parse_params_table(self, text: str) -> List[Dict]:
        """解析参数表格"""
        params = []
        lines = text.strip().split("\n")
        for line in lines:
            # 匹配表格行: | param_name | type | required | description |
            match = re.match(r'\|\s*(\w+)\s*\|\s*(\w+)\s*\|\s*(\S+)\s*\|\s*(.+?)\s*\|', line)
            if match:
                params.append({
                    "name": match.group(1),
                    "type": match.group(2),
                    "required": match.group(3) == "是",
                    "description": match.group(4).strip(),
                })
        return params

    def _parse_capabilities_table(self, text: str) -> List[Dict]:
        """解析能力清单表格"""
        capabilities = []
        lines = text.strip().split("\n")
        for line in lines:
            # 匹配表格行: | 能力 | 工具函数 | 说明 |
            match = re.match(r'\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|', line)
            if match:
                capabilities.append({
                    "ability": match.group(1).strip(),
                    "function": match.group(2).strip(),
                    "description": match.group(3).strip(),
                })
        return capabilities

    def match_skill(self, user_input: str, current_plan: Optional[List] = None) -> Optional[Dict]:
        """
        根据用户输入匹配最合适的 Skill

        匹配策略：
        1. 关键词匹配：统计每个 Skill 的触发关键词命中数
        2. 选择命中数最多的 Skill
        3. 如果没有命中，返回 None（表示不使用 Skill，通用处理）

        Args:
            user_input: 用户输入文本
            current_plan: 当前规划（用于重规划场景，可影响匹配）

        Returns:
            匹配的 Skill 对象，或 None
        """
        if not self._loaded:
            self.load_all()

        best_skill = None
        best_score = 0

        for skill_id, skill in self.skills.items():
            keywords = skill.get("trigger_keywords", [])
            score = sum(1 for kw in keywords if kw in user_input)

            if score > best_score:
                best_score = score
                best_skill = skill

        if best_skill and best_score > 0:
            logger.info(f"Skill 匹配成功 | skill={best_skill['id']} | score={best_score}")
            return best_skill

        logger.info(f"未匹配到特定 Skill | input={user_input[:50]}...")
        return None

    def get_skill(self, skill_id: str) -> Optional[Dict]:
        """按 ID 获取 Skill"""
        if not self._loaded:
            self.load_all()
        return self.skills.get(skill_id)

    def get_all_skills(self) -> List[Dict]:
        """获取所有已加载的 Skill"""
        if not self._loaded:
            self.load_all()
        return list(self.skills.values())

    def get_skill_names(self) -> List[str]:
        """获取所有 Skill 名称列表"""
        if not self._loaded:
            self.load_all()
        return [s["name"] for s in self.skills.values()]

    def get_query_filters(self, skill: Dict) -> Dict:
        """
        从 Skill 的能力清单中提取查询过滤器

        解析能力清单中的函数调用描述，转换为 mockfunction 的查询参数。
        例如：
        - "query_attractions(family_friendly=True)" → {"attractions": {"suitable_for": ["family", "child"]}}
        - "query_restaurants(kids_friendly=True)" → {"restaurants": {"suitable_for": ["family"]}}

        Returns:
            {
                "attractions": {"suitable_for": [...]},
                "restaurants": {"suitable_for": [...]},
                "activities": {"suitable_for": [...]},
                "cafes": {"suitable_for": [...]},
            }
        """
        filters = {
            "attractions": {"suitable_for": []},
            "restaurants": {"suitable_for": []},
            "activities": {"suitable_for": []},
            "cafes": {"suitable_for": []},
        }

        scenario = skill.get("scenario", "")
        capabilities = skill.get("capabilities", [])

        # 根据场景设置默认 suitable_for
        scenario_map = {
            "family": ["family", "child"],
            "friends": ["friends"],
            "couple": ["couple"],
        }
        default_suitable = scenario_map.get(scenario, [])

        # 按能力清单逐项解析
        for cap in capabilities:
            func = cap.get("function", "")
            ability = cap.get("ability", "")

            if "attraction" in func.lower() or "景点" in ability:
                if "family" in func.lower() or "亲子" in ability:
                    filters["attractions"]["suitable_for"] = ["family", "child"]
                elif "group" in func.lower() or "多人" in ability:
                    filters["attractions"]["suitable_for"] = ["friends"]
                elif "romantic" in func.lower() or "浪漫" in ability:
                    filters["attractions"]["suitable_for"] = ["couple"]
                else:
                    filters["attractions"]["suitable_for"] = default_suitable

            if "restaurant" in func.lower() or "餐厅" in ability:
                if "kids" in func.lower() or "亲子" in ability:
                    filters["restaurants"]["suitable_for"] = ["family"]
                elif "group" in func.lower() or "聚餐" in ability:
                    filters["restaurants"]["suitable_for"] = ["friends"]
                elif "romantic" in func.lower() or "氛围" in ability:
                    filters["restaurants"]["suitable_for"] = ["couple"]
                else:
                    filters["restaurants"]["suitable_for"] = default_suitable

            if "activit" in func.lower() or "活动" in ability:
                if "kids" in func.lower() or "亲子" in ability:
                    filters["activities"]["suitable_for"] = ["child"]
                elif "group" in func.lower() or "多人" in ability:
                    filters["activities"]["suitable_for"] = ["friends"]
                elif "romantic" in func.lower() or "约会" in ability:
                    filters["activities"]["suitable_for"] = ["couple"]
                else:
                    filters["activities"]["suitable_for"] = default_suitable

        # 如果没有从能力清单中解析到，使用默认值
        for key in filters:
            if not filters[key]["suitable_for"] and default_suitable:
                filters[key]["suitable_for"] = default_suitable

        return filters


# ==================== 全局单例 ====================
skill_loader = SkillLoader()

__all__ = ["SkillLoader", "skill_loader"]
