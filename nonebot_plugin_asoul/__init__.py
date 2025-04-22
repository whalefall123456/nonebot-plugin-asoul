"""
@Author: star_482
@Date: 2025/3/28 
@File: __init__.py 
@Description:
"""
import random
import os

from nonebot.internal.matcher import Matcher
from nonebot.log import logger
from nonebot.adapters import Event
from nonebot.adapters.qq import Message, MessageEvent, MessageSegment, GroupAtMessageCreateEvent
from nonebot.params import CommandArg, RawCommand
from nonebot.plugin import PluginMetadata
from nonebot.plugin.on import on_command
from nonebot import require
from nonebot.permission import SUPERUSER

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import on_alconna
from nonebot_plugin_alconna.uniseg import Image, Text, UniMessage

from .config import config, Config
from . import start_up as _
from .utils import open_json, download_img
from .fortune_manager import fortune_manager
from .activity import save_img_activity, save_json_activity, get_relative_content

__plugin_meta__ = PluginMetadata(
    name="asoul插件",
    description="提供与asoul相关服务",
    usage="待定",
    type="application",
    config=Config,
    extra={},
)

my_openid = on_command("我的id", priority=config.command_priority)
quotation = on_command("发病小作文", aliases={"发病"}, priority=config.command_priority)
# add_quotation = on_command("添加发病小作文", aliases={"添加发病"}, permission=SUPERUSER,
#                            priority=config.command_priority)
daily_fortune = on_command("今日运势", aliases={"抽签"}, priority=config.command_priority)

week_activity = on_command("本周日程", aliases={"日程"}, priority=config.command_priority)
add_activity = on_command("添加日程", priority=config.command_priority, permission=SUPERUSER)


@my_openid.handle()
async def _(event: Event):
    uid = event.get_user_id()
    await quotation.finish(f"你的唯一id是{uid}")


@quotation.handle()
async def _(event: Event):
    data: dict = open_json("quotation.json")
    data_list = list(data.values())
    reply = random.choice(data_list)
    await quotation.finish(reply)


@daily_fortune.handle()
async def _(event: GroupAtMessageCreateEvent):
    gid = event.group_openid
    uid = event.get_user_id()
    if fortune_manager.check_data(gid, uid):
        # 执行抽签
        img_path = fortune_manager.do_draw(gid, uid)
        message = UniMessage(Image(path=img_path))
        message.append(Text("✨今日运势✨\n"))
        fortune_manager.save_data()
        await message.send()
    else:
        message = UniMessage(Text("你今天抽过签了，再给你看一次哦🤗\n"))
        img_path = os.path.join(config.data_path, f"resource/out/{gid}_{uid}.png")
        message.append(Image(path=img_path))
        await message.send()


@week_activity.handle()
async def _(event: GroupAtMessageCreateEvent):
    img_path = config.data_path + "/activity/new_activity.jpg"
    content = get_relative_content()
    text = ""
    logger.info(content)
    if content["today"]:
        text = text + "今天的安排有：" + ",\n ".join(content["today"])
    if content["tomorrow"]:
        text = text + "\n明天的安排有：" + ",\n ".join(content["tomorrow"])
    message = UniMessage(Text(text))
    message.append(Image(path=img_path))
    await message.send()


@add_activity.handle()
async def _(event: GroupAtMessageCreateEvent, arg: Message = CommandArg()):
    msg = event.get_message()
    image_segment = next((seg for seg in msg if seg.type == "image"), None)
    if image_segment:
        # 如果有图片，直接记录
        image_url = image_segment.data["url"]
        if save_img_activity(image_url):
            await add_activity.finish("日程已记录")
    elif msg[0].data["text"]:
        if save_json_activity(arg[0].data["text"]):
            await add_activity.finish("日程已记录")
    # logger.info(msg[0].data["text"])
    # logger.info(arg[0])
    await add_activity.finish("日程添加失败，请检查")
