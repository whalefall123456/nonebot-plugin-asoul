"""
@Author: star_482
@Date: 2026/5/18
@File: commands
@Description: NoneBot 命令注册层——将 DianaSession 暴露为 QQ Bot 指令.
"""

import asyncio
import logging
from collections import OrderedDict
from pathlib import Path

from nonebot import get_driver
from nonebot.adapters import Event
from nonebot.internal.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.plugin.on import on_command
from nonebot.adapters.qq import Message, MessageSegment

from ..config import config

logger = logging.getLogger(__name__)

from .session import DianaSession, shutdown
from .exceptions import DianaError

# ── stat 变化的中文标签和图标 ──
_CHANGE_LABELS = [
    ("hunger", "饱腹", "🍽️"), ("mood", "心情", "😊"),
    ("energy", "体力", "⚡"), ("closeness", "亲密度", "💕"),
    ("coins", "金币", "💰"),
]

# ── 用户缓存 ──

USER_CACHE: OrderedDict[str, DianaSession] = OrderedDict()
CACHE_MAX_SIZE = 50
USER_CACHE_LOCK = asyncio.Lock()


async def get_session(user_id: str) -> DianaSession:
    """获取或创建 DianaSession，LRU 淘汰."""
    if user_id in USER_CACHE:
        USER_CACHE.move_to_end(user_id)
        return USER_CACHE[user_id]
    async with USER_CACHE_LOCK:
        if user_id in USER_CACHE:
            USER_CACHE.move_to_end(user_id)
            return USER_CACHE[user_id]
        if len(USER_CACHE) >= CACHE_MAX_SIZE:
            oldest_key, oldest_session = USER_CACHE.popitem(last=False)
            try:
                await oldest_session.close()
            except Exception:
                logger.exception("DianaSession close() failed during eviction for user=%s", oldest_key)
        USER_CACHE[user_id] = DianaSession(user_id=user_id)
    return USER_CACHE[user_id]


# ── MD 消息构造 ──

def _md_image(url: str, width: int, height: int, alt: str = "") -> str:
    """生成 QQ Markdown 图片字面量."""
    if not url or width <= 0 or height <= 0:
        return ""
    return f"![{alt} #{width}px #{height}px]({url})"


def _changes_line(changes: dict) -> str:
    """stat 变化 → 单行文本：🍽️ 饱腹 +25  ·  😊 心情 +15."""
    parts = []
    for key, label, icon in _CHANGE_LABELS:
        val = changes.get(key, 0)
        if val == 0:
            continue
        sign = "+" if val > 0 else ""
        parts.append(f"{icon} {label} {sign}{val}")
    return "  ·  ".join(parts) if parts else ""


def _build_interaction_md(result: dict) -> str | None:
    """构建互动结果 MD。COS 不可用时返回 None 触发降级."""
    img_url = result.get("image_url")
    if not img_url:
        return None  # COS miss → 降级为本地图片

    lines = []

    # 交互卡片图
    img_line = _md_image(img_url,
                         result.get("image_width", 0),
                         result.get("image_height", 0))
    if img_line:
        lines.append(img_line)
        lines.append("")

    # 对话文本
    if dialogue := result.get("dialogue"):
        lines.append(f"> {dialogue}")
        lines.append("")

    # stat 变化行
    if changes := result.get("changes"):
        line = _changes_line(changes)
        if line:
            lines.append(line)
            lines.append("")

    # 事件卡片 + 文本
    event_texts = result.get("events_triggered", [])
    event_urls = result.get("event_urls", [])
    for i, evt_text in enumerate(event_texts):
        if i < len(event_urls) and event_urls[i]:
            evt_img = _md_image(event_urls[i], 600, 380)
            if evt_img:
                lines.append("---")
                lines.append(evt_img)
                lines.append("")
        lines.append(evt_text)
        lines.append("")

    # 金币掉落
    if coin_bonus := result.get("coin_bonus"):
        lines.append(coin_bonus)
        lines.append("")

    # 换装触发
    if costume_changed := result.get("costume_changed"):
        lines.append(costume_changed)
        lines.append("")

    return "\n".join(lines).strip()


def _build_error_md(result: dict) -> str:
    """构建错误提示 MD."""
    return str(result.get("text", "发生了一个未知错误……"))


def _build_status_md(result: dict) -> str | None:
    """构建状态卡片 MD."""
    img_url = result.get("image_url")
    if not img_url:
        return None
    img_line = _md_image(img_url,
                         result.get("image_width", 0),
                         result.get("image_height", 0))
    if not img_line:
        return None
    lines = [img_line]
    if alerts := result.get("alerts"):
        lines.append("")
        lines.append(f"⚠ {alerts}")
    return "\n".join(lines)


def _build_talk_md(result: dict) -> str | None:
    """构建聊天 MD（梗事件 or 闲谈）."""
    img_url = result.get("image_url")
    if not img_url and result.get("meme_triggered"):
        return None  # 梗事件但 COS miss → 降级
    lines = []
    if img_url:
        img_line = _md_image(img_url, 600, 380)
        if img_line:
            lines.append(img_line)
            lines.append("")
    if text := result.get("text"):
        lines.append(text)
    return "\n".join(lines).strip() if lines else str(result.get("text", "..."))


def _build_costume_md(result: dict) -> str | None:
    """构建衣柜卡片 MD."""
    img_url = result.get("image_url")
    if not img_url:
        return None
    img_line = _md_image(img_url,
                         result.get("image_width", 0),
                         result.get("image_height", 0))
    return img_line or None


async def send_result(result: dict, matcher: Matcher) -> None:
    """根据 result 内容构造 MD 消息发送；COS 不可用时降级为本地图片."""
    from nonebot_plugin_alconna.uniseg import Image, Text, UniMessage

    md_content = None

    # 按消息类型选择 MD 构造器
    if not result.get("success", True):
        md_content = _build_error_md(result)
    elif "changes" in result:
        md_content = _build_interaction_md(result)
    elif "alerts" in result or result.get("stats"):
        md_content = _build_status_md(result)
    elif "meme_triggered" in result:
        md_content = _build_talk_md(result)
    elif "image_url" in result and result.get("image_url"):
        md_content = _build_costume_md(result)
    else:
        md_content = result.get("text") or str(result)

    if md_content:
        await MessageSegment.markdown(md_content).send()
        return

    # ── COS 降级：本地图片 ──
    message = UniMessage()
    if image := result.get("image"):
        message.append(Image(raw=image))
    if text := result.get("text"):
        message.append(Text(text))
    if events := result.get("events_triggered"):
        message.append(Text("\n\n" + "\n".join(events)))
    await message.send()


def _extract_arg(args: Message) -> str:
    return args.extract_plain_text().strip()


def _error_result(exc: DianaError) -> dict:
    return {"success": False, "text": str(exc), "stats": {}}


# ── Shutdown ──

driver = get_driver()


@driver.on_shutdown
async def _shutdown() -> None:
    try:
        for session in USER_CACHE.values():
            try:
                await session.close()
            except Exception:
                logger.exception(
                    "DianaSession close() failed during shutdown for user=%s",
                    getattr(getattr(session, "pet", None), "user_id", "?"),
                )
    finally:
        await shutdown()


# ── 命令注册 ──

diana_status = on_command("然然状态", aliases={"状态", "我的然然", "然然信息"}, priority=config.command_priority)
diana_wardrobe = on_command("然然衣柜", aliases={"服装", "衣柜", "换装列表"}, priority=config.command_priority)
diana_feed = on_command("喂食", aliases={"喂", "吃", "投喂"}, priority=config.command_priority)
diana_play = on_command("玩耍", aliases={"玩"}, priority=config.command_priority)
diana_work = on_command("打工", aliases={"直播", "工作"}, priority=config.command_priority)
diana_costume = on_command("换装", aliases={"换上", "穿"}, priority=config.command_priority)
diana_unlock = on_command("解锁", aliases={"购买"}, priority=config.command_priority)
diana_talk = on_command("然然", aliases={"然然聊天"}, priority=config.command_priority)
diana_interact = on_command("互动", aliases={"撒娇", "和然然互动"}, priority=config.command_priority)
diana_daily = on_command("日常", aliases={"日常活动"}, priority=config.command_priority)
diana_help = on_command("然然帮助", aliases={"宠物帮助", "然然指令"}, priority=config.command_priority)


# ── 互动 handler（5 个统一路径：interact）──

@diana_feed.handle()
async def _(event: Event, matcher: Matcher, args: Message = CommandArg()):
    action_id = _extract_arg(args)
    if not action_id:
        await diana_feed.finish("要吃什么呢？比如：/吃 鸡胸肉、/吃 小草莓、/吃 薯片")
    session = await get_session(event.get_user_id())
    try:
        result = await session.interact(action_id)
    except DianaError as exc:
        result = _error_result(exc)
    await send_result(result, matcher)


@diana_play.handle()
async def _(event: Event, matcher: Matcher, args: Message = CommandArg()):
    action_id = _extract_arg(args)
    if not action_id:
        await diana_play.finish("玩什么呢？比如：/玩 连连看、/玩 宅舞一支、/玩 你画我猜")
    session = await get_session(event.get_user_id())
    try:
        result = await session.interact(action_id)
    except DianaError as exc:
        result = _error_result(exc)
    await send_result(result, matcher)


@diana_work.handle()
async def _(event: Event, matcher: Matcher, args: Message = CommandArg()):
    action_id = _extract_arg(args)
    if not action_id:
        await diana_work.finish("做什么工作呢？比如：/打工 日常直播、/打工 生日会直播、/打工 团播")
    session = await get_session(event.get_user_id())
    try:
        result = await session.interact(action_id)
    except DianaError as exc:
        result = _error_result(exc)
    await send_result(result, matcher)


@diana_interact.handle()
async def _(event: Event, matcher: Matcher, args: Message = CommandArg()):
    action_id = _extract_arg(args)
    if not action_id:
        await diana_interact.finish("要和然然做什么互动呢？比如：/互动 摸摸头、/互动 Mua、/互动 喊一米八")
    session = await get_session(event.get_user_id())
    try:
        result = await session.interact(action_id)
    except DianaError as exc:
        result = _error_result(exc)
    await send_result(result, matcher)


@diana_daily.handle()
async def _(event: Event, matcher: Matcher, args: Message = CommandArg()):
    action_id = _extract_arg(args)
    if not action_id:
        await diana_daily.finish("和然然一起做什么呢？比如：/日常 休息、/日常 逛街、/日常 刷B站")
    session = await get_session(event.get_user_id())
    try:
        result = await session.interact(action_id)
    except DianaError as exc:
        result = _error_result(exc)
    await send_result(result, matcher)


# ── 换装 handler（不走互动管道）──

@diana_costume.handle()
async def _(event: Event, matcher: Matcher, args: Message = CommandArg()):
    name = _extract_arg(args)
    session = await get_session(event.get_user_id())
    if not name:
        result = await session.random_outfit()
    elif matched := session.match_costume(name):
        result = await session.change_outfit(matched["id"])
    else:
        result = {"success": False, "text": f"没有找到'{name}'这件服装呢……"}
    await send_result(result, matcher)


@diana_unlock.handle()
async def _(event: Event, matcher: Matcher, args: Message = CommandArg()):
    name = _extract_arg(args)
    session = await get_session(event.get_user_id())
    if not name:
        locked = [c for c in session.list_costumes() if not c["owned"]]
        if not locked:
            await diana_unlock.finish("你已经解锁了全部服装！")
        lines = ["可解锁的服装："]
        for costume in locked:
            unlock = costume["unlock"]
            if unlock.get("type") == "level":
                condition = f"需要 Lv.{unlock.get('value')}"
            elif unlock.get("type") == "coins":
                condition = f"需要 {unlock.get('value')} 嘉心糖币"
            elif unlock.get("type") == "achievement":
                condition = "成就解锁"
            else:
                condition = "特殊条件"
            lines.append(f"{costume['emoji']} {costume['name']} - {condition}")
        await diana_unlock.finish("\n".join(lines))
    elif matched := session.match_costume(name):
        result = await session.buy_costume(matched["id"])
    else:
        result = {"success": False, "text": f"没有找到'{name}'这件服装呢……"}
    await send_result(result, matcher)


# ── 其他 handler ──

@diana_status.handle()
async def _(event: Event, matcher: Matcher):
    session = await get_session(event.get_user_id())
    result = await session.status()
    await send_result(result, matcher)


@diana_wardrobe.handle()
async def _(event: Event, matcher: Matcher):
    session = await get_session(event.get_user_id())
    result = await session.costume_list_card()
    if not result.get("image_url") and not result.get("image"):
        result["text"] = "（衣柜卡片渲染失败，请稍后再试）"
    await send_result(result, matcher)


@diana_talk.handle()
async def _(event: Event, matcher: Matcher, args: Message = CommandArg()):
    session = await get_session(event.get_user_id())
    result = await session.talk(_extract_arg(args))
    await send_result(result, matcher)


@diana_help.handle()
async def _():
    help_text = (
        "🍓 嘉然 Diana 宠物养成系统\n\n"
        "查看：/然然状态、/然然衣柜\n"
        "喂食：/吃 鸡胸肉、/吃 小草莓、/吃 薯片\n"
        "玩耍：/玩 连连看、/玩 宅舞一支、/玩 你画我猜\n"
        "打工：/打工 日常直播、/打工 团播、/打工 小剧场\n"
        "换装：/换装、/换装 团服、/解锁 春节服\n"
        "互动：/互动 摸摸头、/互动 Mua、/互动 喊一米八\n"
        "日常：/日常 休息、/日常 逛街、/日常 刷B站\n"
        "聊天：/然然 今天想吃什么"
    )
    await diana_help.finish(help_text)
