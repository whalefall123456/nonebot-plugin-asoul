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
    wife_img_dir: str = "wife_img"
    diana_data_dir: str = "diana/data"
    diana_assets_dir: str = "diana/assets"
    diana_saves_dir: str = "diana/saves"
    command_priority: int = 15
    home_url: str = "https://github.com/whalefall123456/nonebot-plugin-asoul"
    whateat_cd: int = 10
    whateat_max: int = 0

    #R2-bucket（兼容 S3 协议的对象存储：Cloudflare R2 / 腾讯云 COS）
    r2_token: str
    r2_id: str
    r2_key: str
    r2_url: str
    r2_bucket_name: str = "diana-image"
    r2_public_url: str
    # region：R2 用 "auto"；COS 必须填实际区域（如 ap-guangzhou），否则 SigV4 签名失败
    r2_region: str = "auto"


config = get_plugin_config(Config)
