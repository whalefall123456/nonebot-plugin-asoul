"""持久化与工具函数."""

import json
import os
import time
from pathlib import Path
from typing import Optional

from .core import PetState

# ── 存档 schema 版本号 ──
# 新增字段时递增，并配套在 _migrate_save() 中追加 v(N-1) → vN 迁移逻辑。
SAVE_VERSION = 1

# ── 项目根目录（diana/ 的父目录）──
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# ── 内置默认路径 ──
_DEFAULT_DATA_DIR = _PROJECT_ROOT / "data"
_DEFAULT_ASSETS_DIR = _PROJECT_ROOT / "assets"
_DEFAULT_SAVES_DIR = Path(os.getcwd()) / "saves"

# ── 运行时配置（由 configure() 修改）──
_config = {
    "data_dir": _DEFAULT_DATA_DIR,
    "assets_dir": _DEFAULT_ASSETS_DIR,
    "saves_dir": _DEFAULT_SAVES_DIR,
}


def configure(
    data_dir: Optional[Path] = None,
    assets_dir: Optional[Path] = None,
    saves_dir: Optional[Path] = None,
):
    """统一配置所有路径（在 DianaPet 初始化时自动调用）."""
    if data_dir is not None:
        _config["data_dir"] = Path(data_dir)
    if assets_dir is not None:
        _config["assets_dir"] = Path(assets_dir)
    if saves_dir is not None:
        _config["saves_dir"] = Path(saves_dir)


def get_data_dir() -> Path:
    return _config["data_dir"]


def get_assets_dir() -> Path:
    return _config["assets_dir"]


def get_saves_dir() -> Path:
    d = _config["saves_dir"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def today_str() -> str:
    """返回今天的日期字符串 YYYY-MM-DD."""
    return time.strftime("%Y-%m-%d", time.localtime())


def now_ts() -> float:
    return time.time()


def save_pet(pet: PetState, save_dir: Optional[Path] = None) -> Path:
    """保存宠物状态到 JSON 文件."""
    if save_dir is None:
        save_dir = get_saves_dir()
    save_dir.mkdir(parents=True, exist_ok=True)
    filepath = save_dir / f"{pet.user_id}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(pet.to_dict(), f, ensure_ascii=False, indent=2)
    return filepath


def load_pet(user_id: str, save_dir: Optional[Path] = None) -> Optional[PetState]:
    """从 JSON 文件加载宠物状态."""
    if save_dir is None:
        save_dir = get_saves_dir()
    filepath = save_dir / f"{user_id}.json"
    if not filepath.exists():
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    # 惰性迁移：旧存档先转版本，下次 _save() 时由 to_dict() 自然落盘为新版本。
    data = _migrate_save(data)
    return PetState.from_dict(data)


def _migrate_save(data: dict) -> dict:
    """存档 schema 版本迁移.

    - 缺 version 字段 ⇒ 视为 v0（最旧的存档）。
    - 当前只支持 v0 → v1，迁移函数把 version 字段补齐。
    - 落盘交由下一次 save_pet()（由 to_dict() 写入 SAVE_VERSION）。
    """
    if "version" not in data:
        data["version"] = 0
    # 未来新增 v2、v3 字段时，在此处追加 chain migration。
    return data


def delete_pet(user_id: str, save_dir: Optional[Path] = None) -> bool:
    """删除宠物存档."""
    if save_dir is None:
        save_dir = get_saves_dir()
    filepath = save_dir / f"{user_id}.json"
    if filepath.exists():
        os.remove(filepath)
        return True
    return False


def list_pets(save_dir: Optional[Path] = None) -> list[str]:
    """列出所有已保存的宠物 user_id."""
    if save_dir is None:
        save_dir = get_saves_dir()
    if not save_dir.exists():
        return []
    return [f.stem for f in save_dir.glob("*.json")]
