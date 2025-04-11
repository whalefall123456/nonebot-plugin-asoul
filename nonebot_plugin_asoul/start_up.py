"""
@Author: star_482
@Date: 2025/3/28 
@File: start_up 
@Description:
"""
import asyncio
import json
import os

import httpx
from nonebot import get_driver
from nonebot.log import logger
from .config import config

base_url = "https://raw.githubusercontent.com/whalefall123456/nonebot-plugin-asoul/main/resource/"


async def check_file():
    data_path = config.data_path
    if not os.path.exists(data_path):
        os.makedirs(data_path)
    quotation_path = os.path.join(data_path, "quotation.json")
    if not os.path.exists(quotation_path):
        data = await download_file(base_url=base_url)
        with open(quotation_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)


async def download_file(base_url: str):
    async def _download(client: httpx.AsyncClient, name: str):
        url = base_url + name
        resp = await client.get(url, timeout=20, follow_redirects=True)
        if resp.raise_for_status():
            logger.debug(f"{url} download success!")
            return resp.content
        else:
            logger.warning(f"{url} download failed!")

    async with httpx.AsyncClient() as client:
        if content := await _download(client, "quotation.json"):
            data = json.loads(content.decode("utf-8"))
            return data
        else:
            return


driver = get_driver()


@driver.on_startup
async def on_startup():
    logger.info("检查json文件")
    task = asyncio.create_task(check_file())
    await task
