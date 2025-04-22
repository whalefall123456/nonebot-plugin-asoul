"""
@Author: star_482
@Date: 2025/4/11 
@File: fortune_manager 
@Description:抽签相关的类和方法
"""
import json
import os
import random
from datetime import date
from .utils import open_json, drawing
from .config import config


class FortuneManager:
    def __init__(self):
        self.fortune_data_path = os.path.join(config.data_path, "resource/fortune_data.json")
        self.fortune_data = {}
        self.copywriter = open_json("resource/fortune/copywriting.json")
        self.load_data()

    def check_data(self, gid, uid):
        if gid not in self.fortune_data:
            self.fortune_data[gid] = {}
        if uid not in self.fortune_data[gid]:
            self.fortune_data[gid][uid] = None
        last_sign_date = self.fortune_data[gid][uid]
        today_date = date.today()
        if last_sign_date != today_date.isoformat():
            # 第一次抽签或者今天第一次
            return True
        return False

    def do_draw(self, gid, uid):
        title, text = self.get_copywriting()
        out_dir = drawing(gid, uid, title, text)
        today_date = date.today()
        self.fortune_data[gid][uid] = today_date.isoformat()
        return out_dir

    def get_copywriting(self):
        """
        Read the copywriting.json, choice a luck with a random content
        """
        content = self.copywriter.get("copywriting")
        luck = random.choice(content)
        title: str = luck.get("good-luck")
        text: str = random.choice(luck.get("content"))
        return title, text

    def load_data(self):
        if not os.path.exists(self.fortune_data_path):
            os.makedirs(os.path.dirname(self.fortune_data_path), exist_ok=True)
            with open(self.fortune_data_path, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=4)

        with open(self.fortune_data_path, "r", encoding="utf-8") as f:
            self.fortune_data = json.load(f)

    def save_data(self):
        with open(self.fortune_data_path, "w", encoding="utf-8") as f:
            json.dump(self.fortune_data, f, ensure_ascii=False, indent=4)


fortune_manager = FortuneManager()
