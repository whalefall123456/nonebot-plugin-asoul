"""
@Author: star_482
@Date: 2025/3/28 
@File: config 
@Description:
"""
from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    data_path: str = "./data/asoul"
    command_priority: int = 15
    home_url: str = "https://github.com/whalefall123456/nonebot-plugin-asoul"


config = get_plugin_config(Config)
