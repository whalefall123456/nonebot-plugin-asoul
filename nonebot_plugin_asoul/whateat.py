import os
import time
import secrets
from datetime import date
from pathlib import Path
from typing import Literal

from nonebot import get_driver
from nonebot.adapters import Event
from nonebot.adapters.qq import MessageSegment
from nonebot.adapters.qq.models import (
    Action,
    Button,
    InlineKeyboard,
    InlineKeyboardRow,
    MessageKeyboard,
    Permission,
    RenderData,
)
from nonebot_plugin_alconna import Alconna, on_alconna
from nonebot_plugin_alconna.uniseg import Image, Text, UniMessage

from .config import config
from .storage import get_bucket, KEY_PREFIX, manifest

NICKNAME = list(get_driver().config.nickname)
BOT_NAME = NICKNAME[0] if NICKNAME else "然然"

# 全局 CD（秒）
_cd_last: float = 0.0
# 每日用户使用次数 {date_str: {user_id: count}}
_daily_count: dict[str, dict[str, int]] = {}
# 达到上限时的随机回复
MAX_MSG = [
    "你今天吃的够多了！不许再吃了(´-ωก`)",
    "吃吃吃，就知道吃，你都吃饱了！明天再来(▼皿▼#)",
    "(*｀へ´*)你猜我会不会再给你发好吃的图片",
    f"没得吃的了，{BOT_NAME}的食物都被你这坏蛋吃光了！",
    "你在等我给你发好吃的？做梦哦！你都吃那么多了，不许再吃了！ヽ(≧Д≦)ノ",
]

_res_path = "data/whateat_pic"


def _get_today() -> str:
    return date.today().isoformat()


def _check_ismax(event: Event) -> bool:
    """检查用户是否达到每日次数上限，未达上限则计数+1。"""
    max_count = config.whateat_max
    if max_count == 0:
        return False
    today = _get_today()
    user_id = event.get_user_id()
    if today not in _daily_count:
        _daily_count.clear()
        _daily_count[today] = {}
    day_data = _daily_count[today]
    if user_id not in day_data:
        day_data[user_id] = 0
    if day_data[user_id] < max_count:
        day_data[user_id] += 1
        return False
    return True


def _check_cd() -> tuple[bool, float]:
    """检查全局 CD，返回 (是否在CD中, 剩余秒数)。"""
    global _cd_last
    cd = config.whateat_cd
    now = time.time()
    elapsed = now - _cd_last
    if elapsed < cd:
        return True, cd - elapsed
    _cd_last = now
    return False, 0.0


def _random_pic(menu_type: Literal["drink", "eat"]) -> tuple[Path, str]:
    """从本地随机选取一张图片，返回 (路径, 名称)。"""
    pic_dir = Path(_res_path) / f"{menu_type}_pic"
    pic_list = os.listdir(pic_dir)
    pic_name = secrets.choice(pic_list)
    pic_path = pic_dir / pic_name
    return pic_path, Path(pic_name).stem


async def _send_whateat(menu_type: Literal["drink", "eat"], action_verb: str, matcher):
    """eat 和 drink 的共用发送逻辑。"""
    # CD 和上限检查已在各自 handler 中完成
    bucket = get_bucket()
    prefix = KEY_PREFIX["whateat_eat"] if menu_type == "eat" else KEY_PREFIX["whateat_drink"]
    command = "/今天吃什么" if menu_type == "eat" else "/今天喝什么"

    pic_path, pic_name = _random_pic(menu_type)
    url = await bucket.get_or_upload_file(pic_path, prefix=prefix)

    if url is not None:
        key = f"{prefix}/{pic_path.name}"
        entry = manifest.get_static(key)
        w = entry.get("width", 0) if entry else 0
        h = entry.get("height", 0) if entry else 0
        md_img = bucket.build_md_image(url, w, h, pic_name)
        md = f"### 🎉{BOT_NAME}建议你{action_verb}🎉\n\n**{pic_name}**\n\n{md_img}"
        keyboard = MessageKeyboard(
            content=InlineKeyboard(
                rows=[InlineKeyboardRow(buttons=[
                    Button(
                        id=f"whateat_{menu_type}_again",
                        render_data=RenderData(label=f"换一个", visited_label=f"换一个", style=1),
                        action=Action(type=2, permission=Permission(type=2), data=command,
                                      reply=False, enter=True, unsupport_tips=f"请手动发送：{command}"),
                    ),
                ])]
            )
        )
        await matcher.finish(MessageSegment.markdown(md) + MessageSegment.keyboard(keyboard))
    else:
        msg = UniMessage.text(f"🎉{BOT_NAME}建议你{action_verb}🎉\n{pic_name}")
        msg.append(Image(path=str(pic_path)))
        await msg.send()


eat_pic_matcher = on_alconna(
    Alconna("今天吃什么"),
    use_cmd_start=True,
)

drink_pic_matcher = on_alconna(
    Alconna("今天喝什么"),
    use_cmd_start=True,
)

eat_pic_matcher.shortcut(
    r"^[今|明|后]?[天|日]?(早|中|晚)?(上|午|餐|饭|夜宵|宵夜|早|晚)吃(什么|啥|点啥)$",
    fuzzy=False,
)
drink_pic_matcher.shortcut(
    r"^[今|明|后]?[天|日]?(早|中|晚)?(上|午|餐|饭|夜宵|宵夜|早|晚)喝(什么|啥|点啥)$",
    fuzzy=False,
)


@eat_pic_matcher.handle()
async def handle_eat(event: Event):
    if _check_ismax(event):
        await UniMessage.text(secrets.choice(MAX_MSG)).finish()
    in_cd, remain = _check_cd()
    if in_cd:
        await UniMessage.text(f"cd冷却中, 还有{remain:.2f}秒").finish()
    await _send_whateat("eat", "吃", eat_pic_matcher)


@drink_pic_matcher.handle()
async def handle_drink(event: Event):
    if _check_ismax(event):
        await UniMessage.text(secrets.choice(MAX_MSG)).finish()
    in_cd, remain = _check_cd()
    if in_cd:
        await UniMessage.text(f"cd冷却中, 还有{remain:.2f}秒").finish()
    await _send_whateat("drink", "喝", drink_pic_matcher)
