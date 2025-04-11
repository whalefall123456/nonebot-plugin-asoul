"""
@Author: star_482
@Date: 2025/3/30 
@File: utils 
@Description:
"""
import os
import json
import random
from typing import List

from PIL import Image, ImageDraw, ImageFont
from nonebot.log import logger
from .config import config


def open_json(filename: str):
    file_path = os.path.join(config.data_path, filename)
    if not os.path.exists(file_path):
        logger.error(f"文件{file_path}不存在")
        raise FileNotFoundError(f"文件{file_path}不存在")
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def drawing(gid: str, uid: str, title: str, text):
    # 1. Random choice a base image
    imgdir = os.path.join(config.data_path, "resource/img/asoul")
    img_list = os.listdir(imgdir)
    imgPath = os.path.join(imgdir, random.choice(img_list))
    img: Image.Image = Image.open(imgPath).convert("RGB")
    draw = ImageDraw.Draw(img)
    # 3. Draw
    font_size = 45
    color = "#F5F5F5"
    image_font_center = [140, 99]
    fontPath = {
        "title": f"{config.data_path}/resource/font/Mamelon.otf",
        "text": f"{config.data_path}/resource/font/sakura.ttf",
    }
    ttfront = ImageFont.truetype(fontPath["title"], font_size)
    # font_length = ttfront.getsize(title)
    left, top, right, bottom = ttfront.getbbox(title)
    text_width = right - left
    text_height = bottom - top
    draw.text(
        (
            image_font_center[0] - text_width / 2,
            image_font_center[1] - text_height / 2,
        ),
        title,
        fill=color,
        font=ttfront,
    )

    # Text rendering
    font_size = 25
    color = "#323232"
    image_font_center = [140, 297]
    ttfront = ImageFont.truetype(fontPath["text"], font_size)
    slices, result = decrement(text)

    for i in range(slices):
        font_height: int = len(result[i]) * (font_size + 4)
        textVertical: str = "\n".join(result[i])
        x: int = int(
            image_font_center[0]
            + (slices - 2) * font_size / 2
            + (slices - 1) * 4
            - i * (font_size + 4)
        )
        y: int = int(image_font_center[1] - font_height / 2)
        draw.text((x, y), textVertical, fill=color, font=ttfront)

    # Save
    outDir = os.path.join(config.data_path, "resource/out")
    if not os.path.exists(outDir):
        os.makedirs(outDir, exist_ok=True)
    outPath = os.path.join(outDir, f"{gid}_{uid}.png")
    img.save(outPath)
    return outPath


def decrement(text: str):
    """
    Split the text, return the number of columns and text list
    TODO: Now, it ONLY fit with 2 columns of text
    """
    length: int = len(text)
    result: List[str] = []
    cardinality = 9
    if length > 4 * cardinality:
        raise Exception

    col_num: int = 1
    while length > cardinality:
        col_num += 1
        length -= cardinality

    # Optimize for two columns
    space = " "
    length = len(text)  # Value of length is changed!

    if col_num == 2:
        if length % 2 == 0:
            # even
            fillIn = space * int(9 - length / 2)
            return col_num, [
                text[: int(length / 2)] + fillIn,
                fillIn + text[int(length / 2):],
            ]
        else:
            # odd number
            fillIn = space * int(9 - (length + 1) / 2)
            return col_num, [
                text[: int((length + 1) / 2)] + fillIn,
                fillIn + space + text[int((length + 1) / 2):],
            ]

    for i in range(col_num):
        if i == col_num - 1 or col_num == 1:
            result.append(text[i * cardinality:])
        else:
            result.append(text[i * cardinality: (i + 1) * cardinality])

    return col_num, result
