import json
from pathlib import Path
path: Path = Path(__file__).parent
res_path = path / "resource"
voice_path = res_path / "audio"

#获取data.json的dict
def get_json():
    with open(res_path / "data.json",encoding='utf-8') as user_file:
        data:dict = json.load(user_file)
        return data