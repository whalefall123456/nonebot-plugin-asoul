"""
@Author: star_482
@Date: 2025/3/28 
@File: __init__.py 
@Description:
"""
from nonebot.adapters import Event
from nonebot.plugin import PluginMetadata
from nonebot.plugin.on import on_command
from nonebot.permission import SUPERUSER

from .config import config, Config
from . import start_up as _

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

@quotation.handle()
async def _(event: Event):
