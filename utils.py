import io
import json
import random
import sqlite3
from pathlib import Path
from httpx import AsyncClient
from nonebot.adapters.onebot.v11 import MessageSegment

path: Path = Path(__file__).parent
res_path = path / "resource"
voice_path = res_path / "audio"

#获取data.json的dict
def get_json():
    with open(res_path / "data.json",encoding='utf-8') as user_file:
        data:dict = json.load(user_file)
        return data


#内置语音包的发送方法
def get_local_voice(data:dict,character:str,message:list):
    data_chac:dict = data.get(character)
    #给了角色参数，语音参数，并且在json文件中
    if len(message) > 1 and message[1] != "随机" and message[1] in data_chac:
        voice_value = voice_path / character / data_chac[message[1]]
        return MessageSegment.record(voice_value)
    #如果没给参数，或者参数是随机
    else:
        data_list = list(data_chac.values())
        random_num = random.randint(0,len(data_list))
        voice_value = voice_path / character / data_list[random_num]
        return MessageSegment.record(voice_value)

#下载音频
async def download_voice(url: str, client: AsyncClient):
    try:
        headers = {
            "Referer": url,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36",
        }
        re = await client.get(url=url, headers=headers, timeout=60)
        if re.status_code == 200:
            return re.content
        else:
            return re.status_code
    except:
        return 408

#调用api获取语音包发送方法
async def get_api_voice(api:str):
    async with AsyncClient() as client:
        content = await download_voice(api,client)
        if type(content) == int:
            return MessageSegment.text("语音包下载出错")
        else:
            return MessageSegment.record(io.BytesIO(content))

#从数据库中读取url并下载语音
async def get_url_db(name:str):
    conn = sqlite3.connect(res_path / "voicedb.db")
    cur = conn.cursor()
    cursor = cur.execute("select * from urldata where name = ?",[name])
    result = cursor.fetchall()
    #获取随机数
    random_num = random.randint(0, len(result))
    url = result[random_num][5]
    return await get_api_voice(url)



























