"""
@Author: star_482
@Date: 2025/12/11 
@File: eye_shadow 
@Description:
"""
import json
import os
import random
from datetime import date

from nonebot_plugin_alconna.uniseg import Image, Text, UniMessage
from .utils import open_json
from .config import config


def select_random_eyeshadow(using_type: str):
    data: dict = open_json("eyeshadow.json")

    # 检查type参数是否有效，如果无效则在两种类型中随机选择
    if using_type not in ["上班", "日常"]:
        using_type = random.choice(["上班", "日常"])

    # 从对应类型中随机选择一个眼影
    eyeshadows = data[using_type]
    selected_eyeshadow = random.choice(eyeshadows)

    # 提取眼影信息
    name = selected_eyeshadow.get("name", "")
    img_path: str = selected_eyeshadow.get("img_path", "")

    # 构造返回文本
    text = f"今日{using_type}眼影推荐:\n名称: {name}\n"

    message = UniMessage(Text(text))
    full_img_path: str = os.path.join(config.data_path, img_path)
    if img_path and os.path.exists(full_img_path):
        message.append(Image(path=full_img_path))
    return message
