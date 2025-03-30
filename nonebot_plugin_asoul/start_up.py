"""
@Author: star_482
@Date: 2025/3/28 
@File: start_up 
@Description:
"""
import asyncio
import os
from nonebot import get_driver
from nonebot.log import logger
from .config import config


async def check_file():
    data_path = config.data_path
    if not os.path.exists(data_path):
        os.makedirs(data_path)
    quotation_path = os.path.join(data_path, "quotation.json")
    if not os.path.exists(quotation_path):
        with open(quotation_path, 'w') as f:
            pass  # Create an empty file


driver = get_driver()


@driver.on_startup
async def on_startup():
    logger.info("新建json文件")
    task = asyncio.create_task(check_file())
    await task
