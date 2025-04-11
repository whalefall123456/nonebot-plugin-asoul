"""
@Author: star_482
@Date: 2025/3/28 
@File: __init__.py 
@Description:
"""
import random
import os
from nonebot.adapters import Event, Message
from nonebot.plugin import PluginMetadata
from nonebot.plugin.on import on_command
from nonebot import require
from nonebot.permission import SUPERUSER

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import on_alconna
from nonebot_plugin_alconna.uniseg import Image, Text, UniMessage

from .config import config, Config
from . import start_up as _
from .utils import open_json
from .fortune_manager import fortune_manager

__plugin_meta__ = PluginMetadata(
    name="asoul插件",
    description="提供与asoul相关服务",
    usage="待定",
    type="application",
    config=Config,
    extra={},
)

quotation = on_command("发病小作文", aliases={"发病"}, priority=config.command_priority)
add_quotation = on_command("添加发病小作文", aliases={"添加发病"}, permission=SUPERUSER,
                           priority=config.command_priority)
daily_fortune = on_command("今日运势", aliases={"抽签"}, priority=config.command_priority)


@quotation.handle()
async def _(event: Event):
    data: dict = open_json("quotation.json")
    data_list = list(data.values())
    reply = random.choice(data_list)
    await quotation.finish(reply)


@daily_fortune.handle()
async def _(event: Event):
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
