"""
@Author: star_482
@Date: 2026/5/18
@File: diana_pet
@Description:
"""
from pathlib import Path

from nonebot import get_driver
from nonebot.adapters import Event
from nonebot.internal.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.plugin.on import on_command
from nonebot.adapters.qq import Message
from nonebot_plugin_alconna.uniseg import Image, Text, UniMessage

from .config import config
from .diana.api import DianaPet, shutdown

USER_CACHE: dict[str, DianaPet] = {}
CACHE_MAX_SIZE = 500


def _diana_data_dir() -> Path:
    return Path(config.data_path) / config.diana_data_dir


def _diana_assets_dir() -> Path:
    return Path(config.data_path) / config.diana_assets_dir


def _diana_saves_dir() -> Path:
    return Path(config.data_path) / config.diana_saves_dir


async def get_diana(user_id: str) -> DianaPet:
    if user_id not in USER_CACHE:
        if len(USER_CACHE) >= CACHE_MAX_SIZE:
            oldest = next(iter(USER_CACHE))
            await USER_CACHE.pop(oldest).close()
        USER_CACHE[user_id] = DianaPet(
            user_id=user_id,
            data_dir=_diana_data_dir(),
            assets_dir=_diana_assets_dir(),
            saves_dir=_diana_saves_dir(),
        )
    return USER_CACHE[user_id]


async def send_result(result: dict, matcher: Matcher):
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


def _match_costume(diana: DianaPet, costume_name: str) -> dict | None:
    for costume in diana.list_costumes():
        if costume["name"] in costume_name or costume_name in costume["name"]:
            return costume
    return None


driver = get_driver()


@driver.on_shutdown
async def _shutdown():
    for diana in USER_CACHE.values():
        await diana.close()
    await shutdown()


diana_status = on_command("然然状态", aliases={"状态", "我的然然", "然然信息"}, priority=config.command_priority)
diana_wardrobe = on_command("然然衣柜", aliases={"服装", "衣柜", "换装列表"}, priority=config.command_priority)
diana_feed = on_command("喂食", aliases={"喂", "吃", "投喂"}, priority=config.command_priority)
diana_play = on_command("玩耍", aliases={"玩"}, priority=config.command_priority)
diana_work = on_command("打工", aliases={"直播", "工作"}, priority=config.command_priority)
diana_costume = on_command("换装", aliases={"换上", "穿"}, priority=config.command_priority)
diana_unlock = on_command("解锁", aliases={"购买"}, priority=config.command_priority)
diana_talk = on_command("然然", aliases={"然然聊天"}, priority=config.command_priority)
diana_help = on_command("然然帮助", aliases={"宠物帮助", "然然指令"}, priority=config.command_priority)


@diana_status.handle()
async def _(event: Event, matcher: Matcher):
    diana = await get_diana(event.get_user_id())
    result = await diana.status()
    await send_result(result, matcher)


@diana_wardrobe.handle()
async def _(event: Event):
    diana = await get_diana(event.get_user_id())
    img = await diana.costume_list_card()
    message = UniMessage(Text("🎀 然然的衣柜："))
    message.append(Image(raw=img))
    await message.send()


@diana_feed.handle()
async def _(event: Event, matcher: Matcher, args: Message = CommandArg()):
    item = _extract_arg(args)
    if not item:
        await diana_feed.finish("要吃什么呢？比如：/吃 鸡胸肉、/吃 小草莓、/吃 薯片")
    diana = await get_diana(event.get_user_id())
    result = await diana.feed(item)
    await send_result(result, matcher)


@diana_play.handle()
async def _(event: Event, matcher: Matcher, args: Message = CommandArg()):
    activity = _extract_arg(args)
    if not activity:
        await diana_play.finish("玩什么呢？比如：/玩 连连看、/玩 宅舞一支、/玩 你画我猜")
    diana = await get_diana(event.get_user_id())
    result = await diana.play(activity)
    await send_result(result, matcher)


@diana_work.handle()
async def _(event: Event, matcher: Matcher, args: Message = CommandArg()):
    work_name = _extract_arg(args)
    if not work_name:
        await diana_work.finish("做什么工作呢？比如：/打工 日常直播、/打工 生日会直播、/打工 团播")
    diana = await get_diana(event.get_user_id())
    result = await diana.work(work_name)
    await send_result(result, matcher)


@diana_costume.handle()
async def _(event: Event, matcher: Matcher, args: Message = CommandArg()):
    costume_name = _extract_arg(args)
    diana = await get_diana(event.get_user_id())
    if not costume_name:
        result = await diana.random_change_outfit()
    elif matched := _match_costume(diana, costume_name):
        result = await diana.change_outfit(matched["id"])
    else:
        result = {"text": f"没有找到“{costume_name}”这件服装呢……"}
    await send_result(result, matcher)


@diana_unlock.handle()
async def _(event: Event, matcher: Matcher, args: Message = CommandArg()):
    costume_name = _extract_arg(args)
    diana = await get_diana(event.get_user_id())
    if not costume_name:
        locked = [costume for costume in diana.list_costumes() if not costume["owned"]]
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
    elif matched := _match_costume(diana, costume_name):
        result = await diana.buy_costume(matched["id"])
    else:
        result = {"text": f"没有找到“{costume_name}”这件服装呢……"}
    await send_result(result, matcher)


@diana_talk.handle()
async def _(event: Event, matcher: Matcher, args: Message = CommandArg()):
    diana = await get_diana(event.get_user_id())
    result = await diana.talk(_extract_arg(args))
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
        "聊天：/然然 今天想吃什么"
    )
    await diana_help.finish(help_text)
