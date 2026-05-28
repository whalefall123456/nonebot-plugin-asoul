"""
@Author: star_482
@Date: 2025/3/30 
@File: utils 
@Description:
"""
import io
import os
import json
import random
from typing import List

import httpx
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


def save_json(filename: str, data: dict):
    """
    Save a dictionary to a JSON file.

    :param filename: The name of the JSON file.
    :param data: The dictionary to save.
    """
    file_path = os.path.join(config.data_path, filename)
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        # Write the dictionary to the file
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Failed to save JSON to {file_path}: {e}")
        raise


_BASE_IMG_DIR = os.path.join(config.data_path, "resource/img/asoul")
_FONT_TITLE = os.path.join(config.data_path, "resource/font/Mamelon.otf")
_FONT_TEXT = os.path.join(config.data_path, "resource/font/sakura.ttf")


def pick_fortune_base() -> str:
    """随机选择一张抽签底图，返回文件名。"""
    return random.choice(os.listdir(_BASE_IMG_DIR))


def drawing_to_bytes(base_name: str, title: str, text: str):
    """用指定底图合成抽签图，返回 (png_bytes, width, height)。"""
    imgPath = os.path.join(_BASE_IMG_DIR, base_name)
    img: Image.Image = Image.open(imgPath).convert("RGB")
    w, h = img.size
    draw = ImageDraw.Draw(img)

    # 标题
    font_size = 45
    color = "#F5F5F5"
    image_font_center = [140, 99]
    ttfront = ImageFont.truetype(_FONT_TITLE, font_size)
    left, top, right, bottom = ttfront.getbbox(title)
    text_width = right - left
    text_height = bottom - top
    draw.text(
        (image_font_center[0] - text_width / 2, image_font_center[1] - text_height / 2),
        title, fill=color, font=ttfront,
    )

    # 正文
    font_size = 25
    color = "#323232"
    image_font_center = [140, 297]
    ttfront = ImageFont.truetype(_FONT_TEXT, font_size)
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

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), w, h


def drawing(gid: str, uid: str, title: str, text):
    """降级路径：随机底图合成后写盘，返回本地路径。"""
    base_name = pick_fortune_base()
    data, w, h = drawing_to_bytes(base_name, title, text)
    outDir = os.path.join(config.data_path, "resource/out")
    os.makedirs(outDir, exist_ok=True)
    outPath = os.path.join(outDir, f"{gid}_{uid}.png")
    with open(outPath, "wb") as f:
        f.write(data)
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


def download_img(url: str, img_path: str, img_name: str):
    """
    Download an image from a URL and save it to the specified path.

    :param url: The URL of the image.
    :param img_path: The directory where the image will be saved.
    :param img_name: The name of the image file.
    """
    # Ensure the directory exists
    if not os.path.exists(img_path):
        os.makedirs(img_path, exist_ok=True)
    full_path = os.path.join(img_path, img_name)
    try:
        with httpx.Client() as client:
            response = client.get(url, timeout=10.0)
            response.raise_for_status()  # Raise an error for HTTP errors
        # Write the image content to the file
        with open(full_path, "wb") as f:
            f.write(response.content)
        print(f"Image successfully downloaded to {full_path}")
    except httpx.RequestError as e:
        print(f"An error occurred while requesting the image: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
