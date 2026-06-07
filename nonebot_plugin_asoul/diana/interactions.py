"""交互系统：加载物品配置，执行动作，选择对话."""

import random
import time
from pathlib import Path
from typing import Optional

import yaml

from .core import PetState, AchievementFlag
from .utils import today_str
from .exceptions import ActionNotFoundError, InsufficientCoinsError


class InteractionService:
    """处理所有用户交互动作."""

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            data_dir = Path(__file__).parent / "data"
        self.data_dir = Path(data_dir)
        self.items = self._load_yaml("items.yaml")
        self.character = self._load_yaml("character.yaml")
        self.dialogues = self._load_yaml("dialogues.yaml")
        self._dialogue_history: dict[str, list[str]] = {}  # user_id -> recent dialogue keys
        self.exp_multiplier = self.character.get("exp_closeness_multiplier", 2)

    def _load_yaml(self, filename: str) -> dict:
        path = self.data_dir / filename
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    # ── 公共接口 ──

    def list_actions(self, category: Optional[str] = None) -> list[dict]:
        """列出所有可用动作."""
        result = []
        for name, item in self.items.items():
            if category and item.get("category") != category:
                continue
            result.append({
                "id": name,
                "category": item["category"],
                "description": item.get("description", ""),
                "emoji": item.get("emoji", ""),
                "cost": item.get("coins", 0),
            })
        return result

    def execute(self, pet: PetState, action_id: str, costume_service=None) -> dict:
        """执行一个动作，返回结果."""
        if action_id not in self.items:
            raise ActionNotFoundError(action_id)

        item = self.items[action_id]
        category = item["category"]

        # 检查金币
        cost = item.get("coins", 0)
        if cost < 0 and pet.coins + cost < 0:
            raise InsufficientCoinsError

        # 构建 stat 变更：支持 <stat>_random 从列表中随机取值覆盖 <stat>
        stat_keys = ("hunger", "mood", "energy", "closeness", "coins")
        changes = {}
        for key in stat_keys:
            random_key = f"{key}_random"
            if random_key in item:
                changes[key] = random.choice(item[random_key])
            else:
                changes[key] = item.get(key, 0)

        # 应用属性变化
        old_level = pet.level
        pet.modify(
            hunger=changes["hunger"],
            mood=changes["mood"],
            energy=changes["energy"],
            closeness=changes["closeness"],
            coins=changes["coins"],
            exp=changes.get("closeness", item.get("closeness", 0)) * self.exp_multiplier,
        )

        # 等级提升时检查服装解锁
        if costume_service and pet.level > old_level:
            costume_service.auto_unlock_by_level(pet, old_level)

        # 触发 tick
        pet.tick()

        # 记录互动
        pet.interaction_count += 1
        pet.check_daily_decay(today_str())

        # 通用 on_execute 钩子
        on_execute = item.get("on_execute")
        costume_result = None
        if on_execute == "random_costume" and costume_service:
            costume_result = costume_service.random_change(pet)

        # 选择对话
        dialogue = self._pick_dialogue(pet.user_id, category, action_id)

        # 构建返回
        emoji = item.get("emoji", "")
        result = {
            "success": True,
            "text": f"{emoji} {dialogue}",
            "dialogue": dialogue,
            "action": action_id,
            "category": category,
            "stats": {
                "hunger": pet.hunger,
                "mood": pet.mood,
                "energy": pet.energy,
                "closeness": pet.closeness,
                "coins": pet.coins,
                "level": pet.level,
                "exp": pet.exp,
                "title": pet.title,
                "streak_days": pet.streak_days,
            },
            "changes": changes,
            "image_needed": True,
        }
        if costume_result and costume_result["success"]:
            result["costume_changed"] = costume_result["text"]
        return result

    # ── 对话选择 ──

    def _pick_dialogue(self, user_id: str, category: str, action_id: str) -> str:
        """带权重和反重复的对话选择."""
        # 尝试多个键名
        keys_to_try = [
            f"{category}_{action_id}",
            f"{category}_{action_id.split('_')[0]}" if "_" in action_id else None,
        ]
        lines = []
        for key in keys_to_try:
            if key and key in self.dialogues:
                lines = list(self.dialogues[key])
                if lines:
                    break

        if not lines:
            # fallback: 在 dialogues 中搜索匹配
            for key, val in self.dialogues.items():
                if action_id in key and isinstance(val, list):
                    lines = list(val)
                    break

        if not lines:
            return self._random_fallback(category)

        # 避免重复：记录最近使用的对话
        if user_id not in self._dialogue_history:
            self._dialogue_history[user_id] = []

        history = self._dialogue_history[user_id]
        available = [l for l in lines if l not in history[-5:]]  # 最近5条不重复
        if not available:
            available = lines

        chosen = random.choice(available)
        history.append(chosen)
        if len(history) > 50:
            history = history[-50:]
        self._dialogue_history[user_id] = history

        return chosen

    def _random_fallback(self, category: str) -> str:
        """无法匹配时返回通用对话."""
        fallbacks = {
            "food": ["嗯~ 好吃！", "谢谢投喂！", "吃饱了好开心~"],
            "play": ["好好玩！", "再来一次！", "开心开心~"],
            "work": ["努力工作！", "辛苦但值得！", "为了梦想加油！"],
            "social": ["诶嘿~", "谢谢你~", "好开心~"],
            "daily": ["嗯嗯~", "好的~", "知道啦~"],
        }
        return random.choice(fallbacks.get(category, ["好耶！"]))

    # ── 状态描述 ──

    def get_status_text(self, pet: PetState) -> str:
        """生成状态描述文本."""
        mood_emoji = "😊" if pet.mood > 60 else "😐" if pet.mood > 30 else "😢"
        hunger_emoji = "🍽️" if pet.hunger > 60 else "🍴" if pet.hunger > 30 else "🍗"
        energy_emoji = "⚡" if pet.energy > 60 else "🔋" if pet.energy > 30 else "🪫"

        lines = [
            f"{hunger_emoji} 饱腹度：{pet.hunger}/100",
            f"{mood_emoji} 心情：{pet.mood}/100",
            f"{energy_emoji} 体力：{pet.energy}/100",
            f"💕 亲密度：{pet.closeness}/100",
            f"⭐ 等级：{pet.level} | 称号：{pet.title}",
            f"💰 嘉心糖币：{pet.coins}",
            f"🔥 连续互动：{pet.streak_days}天",
        ]
        return "\n".join(lines)

    def get_low_stat_alert(self, pet: PetState) -> Optional[str]:
        """返回低属性警告文本."""
        alerts = []
        if pet.hunger <= 20:
            alerts.append(self._pick_dialogue(pet.user_id, "stat_low", "hunger"))
        if pet.mood <= 20:
            alerts.append(self._pick_dialogue(pet.user_id, "stat_low", "mood"))
        if pet.energy <= 15:
            alerts.append(self._pick_dialogue(pet.user_id, "stat_low", "energy"))
        if pet.closeness <= 20:
            alerts.append(self._pick_dialogue(pet.user_id, "stat_low", "closeness"))
        return "\n".join(alerts) if alerts else None

    def get_greeting(self, pet: PetState) -> str:
        """获取问候语."""
        if "greeting" in self.dialogues:
            return random.choice(self.dialogues["greeting"])
        return "嗨！嘉心糖！🍓"

    def get_idle(self, pet: PetState) -> str:
        """获取闲谈."""
        if "idle" in self.dialogues:
            return random.choice(self.dialogues["idle"])
        return "今天天气真好呢~"
