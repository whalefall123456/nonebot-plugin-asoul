import random
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, GroupMessageEvent, MessageSegment
from pathlib import Path
from src.plugins.nonebot_plugin_asoul.utils import get_json

path: Path = Path(__file__).parent
res_path = path / "resource"
voice_path = res_path / "audio"

voice = on_command("语音包")


@voice.handle()
async def _(event:GroupMessageEvent):
    message = event.get_plaintext().split()[1:]
    if len(message) != 0 :
        character = message[0]
        #读取json文件
        data = get_json()
        #如果角色名字在json中
        if character in data:
            data_chac:dict = data.get(character)
            #给了角色参数，语音参数，并且在json文件中
            if len(message) > 1 and message[1] != "随机" and message[1] in data_chac:
                voice_value = voice_path / character / data_chac[message[1]]
                await voice.finish(MessageSegment.record(voice_value))
            #如果没给参数，或者参数是随机
            else:
                data_list = list(data_chac.values())
                random_num = random.randint(0,len(data_list))
                voice_value = voice_path / character / data_list[random_num]
                await voice.finish(MessageSegment.record(voice_value))
        else:
            await voice.finish(MessageSegment.text("角色语音包不存在"))
    else:
        await voice.finish(MessageSegment.text("请给出角色名"))

