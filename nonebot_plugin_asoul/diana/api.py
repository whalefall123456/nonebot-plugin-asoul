"""对外 API —— QQ Bot 插件调用入口."""

import asyncio
from pathlib import Path
from typing import Optional

from .core import PetState
from .interactions import InteractionService
from .events import EventManager
from .renderer import ImageRenderer
from .costumes import CostumeService
from .utils import save_pet, load_pet, configure as _configure_paths

# ── 模块级共享服务（只初始化一次）──

_services_initialized = False
_interaction_service: Optional[InteractionService] = None
_event_manager: Optional[EventManager] = None
_costume_service: Optional[CostumeService] = None
_renderer: Optional[ImageRenderer] = None

# 渲染并发控制：1C2G 服务器建议 1-2，防止 OOM
_render_semaphore: Optional[asyncio.Semaphore] = None
MAX_CONCURRENT_RENDERS = 2


def _init_shared_services(
    data_dir: Path,
    assets_dir: Path,
    saves_dir: Path,
):
    """初始化所有共享服务（仅在首次调用时执行）."""
    global _services_initialized, _interaction_service, _event_manager
    global _costume_service, _renderer, _render_semaphore

    if _services_initialized:
        return

    # 1. 统一配置所有路径（utils 中的 get_data_dir/get_assets_dir/get_saves_dir 全局生效）
    _configure_paths(data_dir=data_dir, assets_dir=assets_dir, saves_dir=saves_dir)

    # 2. 创建共享服务
    _interaction_service = InteractionService(data_dir)
    _event_manager = EventManager(data_dir)
    _costume_service = CostumeService(data_dir)
    _renderer = ImageRenderer(
        template_dir=data_dir / "templates",
        data_dir=data_dir,
        assets_dir=assets_dir,
    )
    _render_semaphore = asyncio.Semaphore(MAX_CONCURRENT_RENDERS)
    _services_initialized = True


def get_shared_services(
    data_dir: Optional[Path] = None,
    assets_dir: Optional[Path] = None,
    saves_dir: Optional[Path] = None,
):
    """返回共享服务的引用，首次调用时初始化."""
    if not _services_initialized:
        project_root = Path(__file__).parent.parent.resolve()
        if data_dir is None:
            data_dir = project_root / "data"
        if assets_dir is None:
            assets_dir = project_root / "assets"
        if saves_dir is None:
            saves_dir = project_root / "saves"
        _init_shared_services(data_dir, assets_dir, saves_dir)
    return _interaction_service, _event_manager, _costume_service, _renderer, _render_semaphore


async def shutdown():
    """关闭共享资源（进程退出时调用）."""
    global _services_initialized, _renderer, _render_semaphore
    if _renderer:
        await _renderer.close()
        _renderer = None
    _render_semaphore = None
    _services_initialized = False


class DianaPet:
    """嘉然宠物系统——QQ Bot 可直接调用的 API.

    Parameters
    ----------
    user_id : str
        用户唯一标识（QQ 号）。
    data_dir : Path, optional
        YAML 配置目录（items.yaml / events.yaml / dialogues.yaml / templates/ 等）。
        默认：Diana_pet/data/
    assets_dir : Path, optional
        静态资源目录（costume 立绘 PNG）。
        默认：Diana_pet/assets/
    saves_dir : Path, optional
        用户存档目录（{user_id}.json）。
        默认：Diana_pet/saves/
    """

    def __init__(
        self,
        user_id: str,
        data_dir: Optional[Path] = None,
        assets_dir: Optional[Path] = None,
        saves_dir: Optional[Path] = None,
    ):
        self.user_id = user_id

        # 复用共享服务（首次调用时用传入的路径初始化，后续调用忽略路径参数）
        self.interactions, self.events, self.costumes, self.renderer, self._sem = (
            get_shared_services(data_dir, assets_dir, saves_dir)
        )

        # 加载或创建宠物
        pet = load_pet(user_id)
        if pet is None:
            pet = PetState.create(user_id)
        self.pet = pet

    # ── 交互动作 ──

    async def feed(self, item_id: str) -> dict:
        """喂食嘉然."""
        result = self.interactions.execute(self.pet, item_id, self.costumes)
        self.events.track_interaction(self.pet, "food")
        self._check_events(result)
        img = None
        if result["success"]:
            item = self.interactions.items[item_id]
            async with self._sem:
                img = await self.renderer.render_interaction_card(
                    self.pet, item_id, item.get("emoji", "🍽️"),
                    result["dialogue"], result["changes"],
                )
        self._save()
        return {**result, "image": img}

    async def play(self, activity_id: str) -> dict:
        """和嘉然玩耍."""
        result = self.interactions.execute(self.pet, activity_id, self.costumes)
        self.events.track_interaction(self.pet, "play")
        self._check_events(result)
        img = None
        if result["success"]:
            item = self.interactions.items[activity_id]
            async with self._sem:
                img = await self.renderer.render_interaction_card(
                    self.pet, activity_id, item.get("emoji", "🎮"),
                    result["dialogue"], result["changes"],
                )
        self._save()
        return {**result, "image": img}

    async def work(self, work_id: str) -> dict:
        """嘉然打工/直播."""
        result = self.interactions.execute(self.pet, work_id, self.costumes)
        self._check_events(result)
        img = None
        if result["success"]:
            item = self.interactions.items[work_id]
            async with self._sem:
                img = await self.renderer.render_interaction_card(
                    self.pet, work_id, item.get("emoji", "💼"),
                    result["dialogue"], result["changes"],
                )
        self._save()
        return {**result, "image": img}

    async def social(self, action_id: str) -> dict:
        """社交互动."""
        result = self.interactions.execute(self.pet, action_id, self.costumes)
        self._check_events(result)
        img = None
        if result["success"]:
            item = self.interactions.items[action_id]
            async with self._sem:
                img = await self.renderer.render_interaction_card(
                    self.pet, action_id, item.get("emoji", "💬"),
                    result["dialogue"], result["changes"],
                )
        self._save()
        return {**result, "image": img}

    async def daily(self, action_id: str) -> dict:
        """日常活动."""
        result = self.interactions.execute(self.pet, action_id, self.costumes)
        self._check_events(result)
        img = None
        if result["success"]:
            item = self.interactions.items[action_id]
            async with self._sem:
                img = await self.renderer.render_interaction_card(
                    self.pet, action_id, item.get("emoji", "📋"),
                    result["dialogue"], result["changes"],
                )
        self._save()
        return {**result, "image": img}

    # ── 换装 ──

    def list_costumes(self) -> list[dict]:
        """获取所有服装及其解锁状态."""
        return self.costumes.list_costumes(self.pet)

    async def change_outfit(self, costume_id: str) -> dict:
        """手动切换到指定服装."""
        result = self.costumes.change(self.pet, costume_id)
        if result["success"]:
            self._save()
        return result

    async def buy_costume(self, costume_id: str) -> dict:
        """购买/解锁服装."""
        result = self.costumes.unlock(self.pet, costume_id)
        if result["success"]:
            self._save()
        return result

    async def random_change_outfit(self) -> dict:
        """随机换装."""
        result = self.costumes.random_change(self.pet)
        if result["success"]:
            self._save()
        return result

    async def costume_list_card(self) -> bytes:
        """渲染服装选择列表卡片."""
        costumes = self.costumes.list_costumes(self.pet)
        async with self._sem:
            return await self.renderer.render_costume_list(costumes)

    async def talk(self, message: str) -> dict:
        """和嘉然聊天，自动检测关键词触发事件."""
        events = self.events.check_keywords(self.pet, message)
        self.pet.tick()
        img = None
        event_texts = []
        if events:
            for evt in events:
                event_texts.append(evt.get("text", ""))
            async with self._sem:
                img = await self.renderer.render_event_card(events[0])
        elif message.strip():
            # 没有触发事件时返回一条闲谈
            idle = self.interactions.get_idle(self.pet)
            event_texts.append(idle)
        self._save()
        return {
            "text": "\n".join(event_texts) if event_texts else "...",
            "meme_triggered": len(events) > 0,
            "events": events,
            "image": img,
            "stats": self._stats_dict(),
        }

    async def status(self) -> dict:
        """获取嘉然当前状态卡片."""
        self.pet.tick()
        alerts = self.interactions.get_low_stat_alert(self.pet)
        async with self._sem:
            img = await self.renderer.render_status_card(self.pet)
        stats_text = self.interactions.get_status_text(self.pet)
        self._save()
        return {
            "text": stats_text + ("\n\n⚠ " + alerts if alerts else ""),
            "image": img,
            "stats": self._stats_dict(),
            "alerts": alerts,
        }

    async def tick(self) -> dict:
        """时间流逝检查，返回触发的事件."""
        events = self.events.tick(self.pet)
        images = []
        event_texts = []
        for evt in events:
            async with self._sem:
                img = await self.renderer.render_event_card(evt)
            images.append(img)
            event_texts.append(evt.get("text", ""))
        self._save()
        return {
            "events": events,
            "event_texts": event_texts,
            "images": images,
            "stats": self._stats_dict(),
        }

    # ── 工具方法 ──

    def list_items(self, category: Optional[str] = None) -> list[dict]:
        return self.interactions.list_actions(category)

    def get_stats(self) -> dict:
        return self._stats_dict()

    def set_user_birthday(self, birthday: str):
        """设置用户生日 MM-DD，当天触发特殊事件."""
        self.pet.achievement_flags["user_birthday"] = False  # Will check in tick
        self.pet.achievement_flags["user_birthday_date"] = birthday

    async def close(self):
        """关闭当前实例（共享资源在 shutdown() 中统一释放）."""
        self._save()

    # ── 内部 ──

    def _save(self):
        save_pet(self.pet)

    def _stats_dict(self) -> dict:
        return {
            "hunger": self.pet.hunger, "mood": self.pet.mood,
            "energy": self.pet.energy, "closeness": self.pet.closeness,
            "level": self.pet.level, "exp": self.pet.exp,
            "coins": self.pet.coins, "title": self.pet.title,
            "streak_days": self.pet.streak_days,
            "outfit": self.pet.outfit,
            "owned_outfits": self.pet.owned_outfits,
        }

    def _check_events(self, result: dict):
        """检查交互后触发的事件."""
        if result.get("success"):
            events = self.events.tick(self.pet)
            if events:
                result["events_triggered"] = [e.get("text", "") for e in events]
