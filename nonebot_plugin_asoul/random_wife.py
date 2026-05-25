"""
@Author: star_482
@Date: 2026/5/13
@File: random_wife
@Description:
"""
import os
import random
from pathlib import Path
from nonebot import require
require("nonebot_plugin_alconna")
from nonebot_plugin_alconna.uniseg import Image, Text, UniMessage

from .config import config


def _wife_path() -> Path:
    return Path(config.data_path) / config.wife_img_dir


def get_random_wife_message() -> UniMessage:
    wife_path = _wife_path()
    imgs = os.listdir(wife_path)
    img_name = random.choice(imgs)
    img = wife_path / img_name
    notice = "你今日抽取的老婆是" + os.path.splitext(img_name)[0]
    message = UniMessage(Text(notice))
    message.append(Image(path=img))
    return message
