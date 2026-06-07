"""对外 API —— QQ Bot 插件调用入口."""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from jinja2 import TemplateError

from .core import PetState, AchievementFlag
from .interactions import InteractionService
from .events import EventManager
from .renderer import ImageRenderer
from .costumes import CostumeService
from .utils import save_pet, load_pet, configure as _configure_paths, today_str
from .exceptions import DianaError

logger = logging.getLogger(__name__)

# 渲染层可能抛出的异常类型（Playwright / Jinja2 / 资源 IO / 懒加载失败）。
# 只捕获这些——避免吞掉 AttributeError / TypeError / KeyError 等编程错误。
# 注意：ImportError 也在内——当用户没装 playwright.async_api 时，renderer.py 内部
# `from playwright.async_api import async_playwright` 会抛 ImportError；之前的 `except Exception`
# 兜底承诺"无 Playwright 也能用"在收窄白名单时不能丢这条。
try:
    from playwright.async_api import Error as PlaywrightError
    _RENDER_EXCEPTIONS: tuple[type[BaseException], ...] = (
        PlaywrightError, TemplateError, OSError, asyncio.TimeoutError, ImportError,
    )
except ImportError:  # 没有 Playwright 时只兜底层 IO / 模板错误 + 懒加载失败
    _RENDER_EXCEPTIONS = (TemplateError, OSError, asyncio.TimeoutError, ImportError)

# ── 模块级共享服务（只初始化一次）──

_services_initialized = False
_interaction_service: Optional[InteractionService] = None
_event_manager: Optional[EventManager] = None
_costume_service: Optional[CostumeService] = None
_renderer: Optional[ImageRenderer] = None

# 渲染并发控制：1C2G 服务器建议 1-2，防止 OOM
_render_semaphore: Optional[asyncio.Semaphore] = None
MAX_CONCURRENT_RENDERS = 2

# ── 每用户互斥锁（防同 user_id 并发请求竞态写 PetState）──
_user_locks: dict[str, asyncio.Lock] = {}


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
        # data 与 assets 默认在 diana 包内（与代码一起发布），saves 从插件配置解析。
        package_dir = Path(__file__).parent.resolve()
        if data_dir is None:
            data_dir = package_dir / "data"
        if assets_dir is None:
            assets_dir = package_dir / "assets"
        if saves_dir is None:
            from ..config import config
            saves_dir = Path(config.data_path) / config.diana_saves_dir
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
        默认：diana 包内的 data/ 目录。
    assets_dir : Path, optional
        静态资源目录（costume 立绘 PNG）。
        默认：diana 包内的 assets/ 目录。
    saves_dir : Path, optional
        用户存档目录（{user_id}.json）。
        默认：{config.data_path}/{config.diana_saves_dir}（即 ./data/asoul/diana/saves）。
    """

    def __init__(
        self,
        user_id: str,
        data_dir: Optional[Path] = None,
        assets_dir: Optional[Path] = None,
        saves_dir: Optional[Path] = None,
    ):
        self.user_id = user_id

        # 每用户互斥锁：防止同 user_id 并发请求竞态写 PetState。
        self._lock = _user_locks.setdefault(user_id, asyncio.Lock())

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

    def _handle_interaction_error(self, exc: DianaError) -> dict:
        """将 DianaError 转换为统一的失败返回字典."""
        return {"success": False, "text": str(exc), "stats": {}, "image_needed": False}

    async def feed(self, item_id: str) -> dict:
        """喂食嘉然."""
        async with self._lock:
            try:
                result = self.interactions.execute(self.pet, item_id, self.costumes)
            except DianaError as exc:
                return self._handle_interaction_error(exc)
            self.events.track_interaction(self.pet, "food")
            self._check_events(result)
            img = None
            if result["success"]:
                item = self.interactions.items[item_id]
                try:
                    async with self._sem:
                        img = await self.renderer.render_interaction_card(
                            self.pet, item_id, item.get("emoji", "🍽️"),
                            result["dialogue"], result["changes"],
                        )
                except _RENDER_EXCEPTIONS:
                    logger.exception("Diana render_interaction_card failed for user=%s action=%s", self.pet.user_id, item_id)
                    img = None
            self._save()
            return {**result, "image": img}

    async def play(self, activity_id: str) -> dict:
        """和嘉然玩耍."""
        async with self._lock:
            try:
                result = self.interactions.execute(self.pet, activity_id, self.costumes)
            except DianaError as exc:
                return self._handle_interaction_error(exc)
            self.events.track_interaction(self.pet, "play")
            self._check_events(result)
            img = None
            if result["success"]:
                item = self.interactions.items[activity_id]
                try:
                    async with self._sem:
                        img = await self.renderer.render_interaction_card(
                            self.pet, activity_id, item.get("emoji", "🎮"),
                            result["dialogue"], result["changes"],
                        )
                except _RENDER_EXCEPTIONS:
                    logger.exception("Diana render_interaction_card failed for user=%s action=%s", self.pet.user_id, activity_id)
                    img = None
            self._save()
            return {**result, "image": img}

    async def work(self, work_id: str) -> dict:
        """嘉然打工/直播."""
        async with self._lock:
            try:
                result = self.interactions.execute(self.pet, work_id, self.costumes)
            except DianaError as exc:
                return self._handle_interaction_error(exc)
            self._check_events(result)
            img = None
            if result["success"]:
                item = self.interactions.items[work_id]
                try:
                    async with self._sem:
                        img = await self.renderer.render_interaction_card(
                            self.pet, work_id, item.get("emoji", "💼"),
                            result["dialogue"], result["changes"],
                        )
                except _RENDER_EXCEPTIONS:
                    logger.exception("Diana render_interaction_card failed for user=%s action=%s", self.pet.user_id, work_id)
                    img = None
            self._save()
            return {**result, "image": img}

    async def social(self, action_id: str) -> dict:
        """社交互动."""
        async with self._lock:
            try:
                result = self.interactions.execute(self.pet, action_id, self.costumes)
            except DianaError as exc:
                return self._handle_interaction_error(exc)
            self._check_events(result)
            img = None
            if result["success"]:
                item = self.interactions.items[action_id]
                try:
                    async with self._sem:
                        img = await self.renderer.render_interaction_card(
                            self.pet, action_id, item.get("emoji", "💬"),
                            result["dialogue"], result["changes"],
                        )
                except _RENDER_EXCEPTIONS:
                    logger.exception("Diana render_interaction_card failed for user=%s action=%s", self.pet.user_id, action_id)
                    img = None
            self._save()
            return {**result, "image": img}

    async def daily(self, action_id: str) -> dict:
        """日常活动."""
        async with self._lock:
            try:
                result = self.interactions.execute(self.pet, action_id, self.costumes)
            except DianaError as exc:
                return self._handle_interaction_error(exc)
            self._check_events(result)
            img = None
            if result["success"]:
                item = self.interactions.items[action_id]
                try:
                    async with self._sem:
                        img = await self.renderer.render_interaction_card(
                            self.pet, action_id, item.get("emoji", "📋"),
                            result["dialogue"], result["changes"],
                        )
                except _RENDER_EXCEPTIONS:
                    logger.exception("Diana render_interaction_card failed for user=%s action=%s", self.pet.user_id, action_id)
                    img = None
            self._save()
            return {**result, "image": img}

    # ── 换装 ──

    def list_costumes(self) -> list[dict]:
        """获取所有服装及其解锁状态."""
        return self.costumes.list_costumes(self.pet)

    async def change_outfit(self, costume_id: str) -> dict:
        """手动切换到指定服装."""
        async with self._lock:
            try:
                result = self.costumes.change(self.pet, costume_id)
            except DianaError as exc:
                return {"success": False, "text": str(exc)}
            if result["success"]:
                self._save()
            return result

    async def buy_costume(self, costume_id: str) -> dict:
        """购买/解锁服装."""
        async with self._lock:
            try:
                result = self.costumes.unlock(self.pet, costume_id)
            except DianaError as exc:
                return {"success": False, "text": str(exc)}
            if result["success"]:
                self._save()
            return result

    async def random_change_outfit(self) -> dict:
        """随机换装."""
        async with self._lock:
            result = self.costumes.random_change(self.pet)
            if result["success"]:
                self._save()
            return result

    async def costume_list_card(self) -> bytes | None:
        """渲染服装选择列表卡片，渲染失败时返回 None（调用方需降级为纯文本）."""
        costumes = self.costumes.list_costumes(self.pet)
        try:
            async with self._sem:
                return await self.renderer.render_costume_list(costumes)
        except _RENDER_EXCEPTIONS:
            logger.exception("Diana render_costume_list failed for user=%s", self.pet.user_id)
            return None

    async def talk(self, message: str) -> dict:
        """和嘉然聊天，自动检测关键词触发事件."""
        async with self._lock:
            events = self.events.check_keywords(self.pet, message)
            self.pet.tick()
            self.pet.check_daily_decay(today_str())
            img = None
            event_texts = []
            if events:
                for evt in events:
                    event_texts.append(evt.get("text", ""))
                try:
                    async with self._sem:
                        img = await self.renderer.render_event_card(events[0])
                except _RENDER_EXCEPTIONS:
                    logger.exception("Diana render_event_card failed for user=%s", self.pet.user_id)
                    img = None
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
        async with self._lock:
            self.pet.tick()
            self.pet.check_daily_decay(today_str())
            alerts = self.interactions.get_low_stat_alert(self.pet)
            img = None
            try:
                async with self._sem:
                    img = await self.renderer.render_status_card(self.pet)
            except _RENDER_EXCEPTIONS:
                logger.exception("Diana render_status_card failed for user=%s", self.pet.user_id)
                img = None
            stats_text = self.interactions.get_status_text(self.pet)
            self._save()
            return {
                "text": stats_text + ("\n\n⚠ " + alerts if alerts else ""),
                "image": img,
                "stats": self._stats_dict(),
                "alerts": alerts,
            }

    async def tick(self) -> dict:
        """时间流逝检查，返回触发的事件.

        注意：此处不调 check_daily_decay() —— tick 是被动时间流逝入口，
        若在 on_startup 等场景下与 bot 重启叠加，重复调用会让 streak_days
        在同一天被加 2。streak 更新交由 talk/status/feed/play 等用户主动
        动作触发。
        """
        async with self._lock:
            events = self.events.tick(self.pet)
            images = []
            event_texts = []
            for evt in events:
                img = None
                try:
                    async with self._sem:
                        img = await self.renderer.render_event_card(evt)
                except _RENDER_EXCEPTIONS:
                    logger.exception("Diana render_event_card failed for user=%s", self.pet.user_id)
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

    async def close(self):
        """关闭当前实例（共享资源在 shutdown() 中统一释放）."""
        async with self._lock:
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
