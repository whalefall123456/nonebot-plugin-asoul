"""
@Author: star_482
@Date: 2026/6/4
@File: notifier
@Description: QQ 开播通知器。被 LiveChecker 回调，查订阅群 → 发 Markdown 消息。
"""
from nonebot import get_bot
from nonebot.adapters.qq import Message, MessageSegment
from nonebot.adapters.qq.models import (
    Action,
    Button,
    InlineKeyboard,
    InlineKeyboardRow,
    MessageKeyboard,
    Permission,
    RenderData,
)
from nonebot.log import logger

from .api import LiveInfo
from .manager import manager


def _mk_link_button(url: str) -> Button:
    return Button(
        id="live_goto",
        render_data=RenderData(label="去直播间", visited_label="去直播间", style=1),
        action=Action(
            type=0,
            permission=Permission(type=2),
            data=url,
            unsupport_tips=f"请手动打开：{url}",
        ),
    )


class Notifier:
    """QQ 群 Markdown 通知。"""

    async def on_live_start(self, info: LiveInfo) -> None:
        groups = manager.get_subscribed_groups(info.uid)
        if not groups:
            return

        area = f"{info.parent_area_name}/{info.area_name}".strip("/")
        md = f"## {info.uname} 开播啦！\n\n**{info.title}**\n\n分区：{area}"
        keyboard = MessageKeyboard(
            content=InlineKeyboard(
                rows=[InlineKeyboardRow(buttons=[_mk_link_button(info.url)])]
            )
        )
        message = MessageSegment.markdown(md) + MessageSegment.keyboard(keyboard)

        bot = get_bot()
        for gid in groups:
            try:
                await bot.send_to_group(group_openid=gid, message=message)
            except Exception as e:
                logger.warning(
                    f"发送开播通知失败 gid={gid} uid={info.uid}: {e}"
                )

    async def on_live_stop(self, info: LiveInfo, _old_info: LiveInfo | None = None) -> None:
        pass  # 只做开播通知，下播不提醒
