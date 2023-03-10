import random
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, GroupMessageEvent, MessageSegment
from pathlib import Path
from src.plugins.nonebot_plugin_asoul.utils import get_json, get_local_voice, get_api_voice, get_url_db

path: Path = Path(__file__).parent
res_path = path / "resource"
voice_path = res_path / "audio"

voice = on_command("语音包")

#语音包指令处理模块
@voice.handle()
async def _(event:GroupMessageEvent):
    message = event.get_plaintext().split()[1:]
    if len(message) != 0 :
        character = message[0]
        #读取json文件
        data = get_json()
        #如果角色名字在json中
        if character in data:
            #调用内置语音包发送方法
            await voice.finish(get_local_voice(data,character,message))
        elif character in data["API"]:
            #调用api获取语音并发送
            api = data["API"][character]
            await voice.finish(await get_api_voice(api))
        elif character in data["DB"]:
            #从数据库查取地址
            await voice.finish(await get_url_db(character))
        else:
            await voice.finish(MessageSegment.text("角色语音包不存在"))
    else:
        await voice.finish(MessageSegment.text("请给出角色名"))