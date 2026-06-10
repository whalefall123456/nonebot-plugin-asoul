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
from nonebot.adapters.qq import Message
from nonebot_plugin_alconna.uniseg import Image, Text, UniMessage

from ..config import config

logger = logging.getLogger(__name__)

from .session import DianaSession, shutdown
from .exceptions import DianaError

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


# ── 工具函数 ──

async def send_result(result: dict, matcher: Matcher) -> None:
    """统一发送结果."""
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
async def _(event: Event):
    session = await get_session(event.get_user_id())
    result = await session.costume_list_card()
    message = UniMessage(Text("🎀 然然的衣柜："))
    if img := result.get("image"):
        message.append(Image(raw=img))
    else:
        message.append(Text("\n（衣柜卡片渲染失败，请稍后再试）"))
    await message.send()


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
