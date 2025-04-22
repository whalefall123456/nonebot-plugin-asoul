"""
@Author: star_482
@Date: 2025/4/17 
@File: activity 
@Description:
"""
from nonebot.log import logger
import json
from datetime import date, timedelta
from .utils import download_img, open_json, save_json
from .config import config


def save_img_activity(url: str):
    try:
        today_date = date.today()
        # img_name = today_date.isoformat() + ".png"
        download_img(url, config.data_path + "/activity", "new_activity.jpg")
        return True
    except Exception as e:
        return False


def save_json_activity(content: str):
    data: dict = open_json("activity/activity.json")
    try:
        new_data: dict = json.loads(content)
        for key, value in new_data.items():
            if key in data:
                data[key].extend(value)  # 合并列表
            else:
                data[key] = value  # 新增键值对
        save_json("activity/activity.json", data)
        return True
    except Exception as e:
        return False


def get_relative_content():
    """
    Returns today's and tomorrow's activities from the stored JSON data.
    """
    try:
        # Load the activity data
        data: dict = open_json("activity/activity.json")
        # Get today's and tomorrow's dates
        today = date.today().isoformat().replace("-", ".")
        tomorrow = (date.today() + timedelta(days=1)).isoformat().replace("-", ".")
        # Retrieve activities for today and tomorrow
        today_activities = data.get(today, [])
        tomorrow_activities = data.get(tomorrow, [])
        return {
            "today": today_activities,
            "tomorrow": tomorrow_activities
        }
    except Exception as e:
        return {
            "today": [],
            "tomorrow": []
        }
