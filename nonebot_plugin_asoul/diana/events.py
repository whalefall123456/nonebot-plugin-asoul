"""事件系统：随机事件、关键词检测、特殊日期、成就."""

import random
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from .core import PetState, AchievementFlag
from .utils import today_str


class EventManager:
    """管理所有事件触发和分发."""

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            data_dir = Path(__file__).parent / "data"
        self.data_dir = Path(data_dir)
        raw = self._load_yaml("events.yaml")
        self.random_events: list[dict] = []
        self.meme_events: dict[str, dict] = {}
        self.special_dates: dict[str, dict] = {}
        self.achievements: list[dict] = []
        self._parse(raw)

    def _load_yaml(self, filename: str) -> dict:
        path = self.data_dir / filename
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _parse(self, raw: dict):
        for name, data in raw.get("random", {}).items():
            data = dict(data)
            data["id"] = name
            data["type"] = "random"
            self.random_events.append(data)
        for name, data in raw.get("meme", {}).items():
            data = dict(data)
            data["id"] = name
            data["type"] = "meme"
            keywords = data.pop("keywords", [])
            data["keywords"] = keywords
            for kw in keywords:
                self.meme_events[kw] = data
        for date_str, data in raw.get("special_dates", {}).items():
            data = dict(data)
            data["type"] = "special_date"
            self.special_dates[date_str] = data
        for name, data in raw.get("achievements", {}).items():
            data = dict(data)
            data["id"] = name
            data["type"] = "achievement"
            self.achievements.append(data)

    # ── 公共接口 ──

    def tick(self, pet: PetState) -> list[dict]:
        """每次 tick 时检查所有事件，返回触发的事件列表."""
        triggered = []

        # 随机事件（概率基于 0-100）
        for evt in self.random_events:
            prob = evt.get("probability", 5)
            if random.randint(1, 100) <= prob:
                self._apply_event(pet, evt)
                triggered.append(evt)

        # 特殊日期
        today = today_str()
        today_mmdd = today[5:]  # "MM-DD"
        if today_mmdd in self.special_dates:
            evt = self.special_dates[today_mmdd]
            if today_mmdd not in pet.achievement_flags:
                self._apply_event(pet, evt)
                triggered.append(evt)
                pet.achievement_flags[today_mmdd] = True

        # 成就
        for ach in self.achievements:
            cond = ach.get("condition", {})
            if self._check_achievement(pet, cond):
                ach_key = f"ach_{ach['id']}"
                if ach_key not in pet.achievement_flags:
                    self._apply_event(pet, ach)
                    triggered.append(ach)
                    pet.achievement_flags[ach_key] = True

        return triggered

    def check_keywords(self, pet: PetState, text: str) -> list[dict]:
        """检测用户消息中的关键词，触发对应 meme 事件."""
        triggered = []
        text_lower = text.lower()
        for keyword, evt in self.meme_events.items():
            if keyword.lower() in text_lower or keyword in text:
                evt_key = f"meme_{evt['id']}"
                self._apply_event(pet, evt)
                triggered.append(evt)
                # 记录 meme 触发次数（总计，含重复）
                pet.achievement_flags[AchievementFlag.MEME_TRIGGERS_COUNT] = pet.achievement_flags.get(AchievementFlag.MEME_TRIGGERS_COUNT, 0) + 1
                # 标记首次触发（用于成就判重）
                pet.achievement_flags[evt_key] = True
                break  # 一次只触发一个 meme 事件
        return triggered

    # ── 内部方法 ──

    def _apply_event(self, pet: PetState, evt: dict):
        """将事件的效果应用到宠物."""
        effects = evt.get("effects", {})
        pet.modify(
            hunger=effects.get("hunger", 0),
            mood=effects.get("mood", 0),
            energy=effects.get("energy", 0),
            closeness=effects.get("closeness", 0),
            coins=effects.get("coins", 0),
            exp=effects.get("exp", 0),
        )

    def _check_achievement(self, pet: PetState, cond: dict) -> bool:
        """检查是否满足成就条件."""
        if "streak_days" in cond and pet.streak_days < cond["streak_days"]:
            return False
        if "closeness" in cond and pet.closeness < cond["closeness"]:
            return False
        if "level" in cond and pet.level < cond["level"]:
            return False
        if "interaction_feed_count" in cond:
            feed_count = pet.achievement_flags.get(AchievementFlag.INTERACTION_FEED_COUNT, 0)
            if feed_count < cond["interaction_feed_count"]:
                return False
        if "interaction_play_count" in cond:
            play_count = pet.achievement_flags.get(AchievementFlag.INTERACTION_PLAY_COUNT, 0)
            if play_count < cond["interaction_play_count"]:
                return False
        if "meme_triggers" in cond:
            # 计算触发过多少种不同的 meme（基于 meme_xxx 标记）
            meme_count = sum(1 for k in pet.achievement_flags if k.startswith("meme_") and pet.achievement_flags[k])
            if meme_count < cond["meme_triggers"]:
                return False
        return True

    def track_interaction(self, pet: PetState, category: str):
        """跟踪互动类型计数（用于成就）."""
        if category == "food":
            key = AchievementFlag.INTERACTION_FEED_COUNT
        elif category == "play":
            key = AchievementFlag.INTERACTION_PLAY_COUNT
        else:
            return
        pet.achievement_flags[key] = pet.achievement_flags.get(key, 0) + 1

    def get_random_event_texts(self, pet: PetState) -> list[str]:
        """获取随机闲散对话（不应用效果，仅文本）."""
        texts = []
        for evt in self.random_events:
            if evt.get("probability", 5) >= 8 and random.randint(1, 100) <= 15:
                texts.append(evt.get("text", ""))
        return texts
