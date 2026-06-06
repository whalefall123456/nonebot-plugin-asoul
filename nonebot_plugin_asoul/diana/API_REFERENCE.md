# DianaPet API 参考文档

嘉然（A-SOUL）虚拟宠物养成系统。提供 Python API 给 QQ 聊天机器人框架调用，支持 56 种交互动作、85 个事件、250+ 条对话、5 套服装，HTML -> PNG 卡片渲染。

---

## 目录

1. [快速开始](#快速开始)
2. [架构与设计要点](#架构与设计要点)
3. [DianaPet 类 API 参考](#dianapet-类-api-参考)
4. [物品/动作 ID 列表](#物品动作-id-列表)
5. [服装系统](#服装系统)
6. [事件系统](#事件系统)
7. [对话系统](#对话系统)
8. [属性与升级](#属性与升级)
9. [错误处理](#错误处理)
10. [完整 Bot 插件示例](#完整-bot-插件示例)

---

## 快速开始

### 环境要求

- Python 3.11+
- Conda 环境 `dianapet`，或手动安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 最简示例

```python
import asyncio
from pathlib import Path
from diana.api import DianaPet, shutdown

async def main():
    # 创建宠物，指定各目录路径（不传则使用默认值）
    diana = DianaPet(
        user_id="qq_123456",
        data_dir=Path("./Diana_pet/data"),     # YAML 配置与模板
        assets_dir=Path("./Diana_pet/assets"),  # 服装立绘
        saves_dir=Path("./saves"),              # 用户存档
    )

    # 喂食
    result = await diana.feed("鸡胸肉")
    print(result["text"])          # 文本结果
    print(len(result["image"]))    # PNG 图片字节
    print(result["stats"])         # 当前属性

    # 查看状态
    status = await diana.status()
    print(status["text"])

    await diana.close()

asyncio.run(main())
```

> **重要**: 每个 `DianaPet` 实例绑定一个用户（`user_id`），不要跨用户复用实例。但底层的 YAML 配置和 Chromium 浏览器是模块级单例共享的，只会初始化一次，不会重复消耗内存。
>
> **路径**: 三个路径参数仅在**首次**创建 `DianaPet` 时生效（用于初始化共享服务），后续实例的路径参数会被忽略。

---

## 架构与设计要点

### 模块结构

```
diana/
├── api.py           # DianaPet 类 - 对外唯一入口
├── core.py          # PetState 状态机、属性衰减、等级称号
├── costumes.py      # CostumeService - 服装解锁、切换
├── interactions.py  # InteractionService - 物品加载、动作执行、对话选择
├── events.py        # EventManager - 随机/meme/日期/成就事件
├── renderer.py      # ImageRenderer - Jinja2 + Playwright HTML→PNG
└── utils.py         # JSON 持久化、工具函数
```

### 关键设计

| 项目 | 说明 |
|------|------|
| 属性范围 | 0-100（饱腹/心情/体力/亲密度） |
| 衰减速率 | 饱腹-2.5/h、心情-2/h、体力-1/h、亲密度-3/天（未互动） |
| 升级 | 每 100 经验升 1 级，等级对应称号 |
| 对话 | 加权随机 + 最近 5 条反重复，按 user_id 隔离 |
| 成就 | 10 个成就（连续互动/亲密度/等级/喂食次数等），不重复触发 |
| 服装 | 5 套，解锁方式：默认/等级/金币购买/成就 |
| 服务共享 | InteractionService / EventManager / CostumeService / ImageRenderer 为进程级单例 |
| 渲染并发 | 信号量限制，默认最多 2 个并发渲染（1C2G 安全值） |

### 数据存储

用户存档保存在 `./saves/{user_id}.json`，格式如下：

```json
{
  "version": 1,
  "user_id": "qq_123456",
  "hunger": 80, "mood": 70, "energy": 90, "closeness": 50,
  "level": 1, "exp": 0, "coins": 100,
  "outfit": "default",
  "owned_outfits": ["default"],
  "title": "新来的嘉心糖",
  "interaction_count": 0, "streak_days": 0,
  "last_interaction_date": "2026-05-18",
  "achievement_flags": {}
}
```

> 存档带 `version` 字段。`utils._migrate_save()` 在 `load_pet()` 时把缺 `version` 的旧存档补成 `0`，下次 `_save()` 由 `to_dict()` 自然落盘为 `SAVE_VERSION`。`SAVE_VERSION` 在 `diana/utils.py` 顶部定义，新增字段时递增并配套追加迁移逻辑。

---

## DianaPet 类 API 参考

### 构造函数

```python
diana = DianaPet(
    user_id: str,
    data_dir: Optional[Path] = None,
    assets_dir: Optional[Path] = None,
    saves_dir: Optional[Path] = None,
)
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | `str` | 是 | 用户唯一标识，推荐使用 QQ 号 |
| `data_dir` | `Path` | 否 | YAML 配置和模板目录，默认 `Diana_pet/data/` |
| `assets_dir` | `Path` | 否 | 静态资源目录（服装立绘），默认 `Diana_pet/assets/` |
| `saves_dir` | `Path` | 否 | 用户存档目录（`{user_id}.json`），默认 `Diana_pet/saves/` |

- 若 `{saves_dir}/{user_id}.json` 存在则加载存档，否则创建新宠物
- 新宠物初始属性：饱腹 80 / 心情 70 / 体力 90 / 亲密度 50 / 金币 100 / 等级 1
- **三个路径仅在首次创建 `DianaPet` 时生效**（用于初始化全局共享服务），后续实例的路径参数会被忽略

---

### 1. 喂食 `feed(item_id)`

```python
result = await diana.feed(item_id: str) -> dict
```

**参数**: `item_id` — 食物 ID，见 [食物类](#1-食物类-food)

**返回值**:

```python
{
    "success": True,
    "text": "🍗 嗯~ 好吃！谢谢投喂！",    # 带 emoji 的结果文本
    "dialogue": "嗯~ 好吃！谢谢投喂！",   # 对话文本（不含 emoji）
    "action": "鸡胸肉",
    "category": "food",
    "stats": {                          # 操作后的当前属性
        "hunger": 95, "mood": 85, "energy": 85, "closeness": 58,
        "coins": 88, "level": 1, "exp": 16, "title": "新来的嘉心糖",
        "streak_days": 1
    },
    "changes": {                        # 本次操作造成的属性变化
        "hunger": 25, "mood": 15, "energy": 5, "closeness": 8, "coins": -12
    },
    "image": b"..." or None,            # PNG 图片字节，失败时为 None
    "events_triggered": ["事件文本..."]  # 可能触发的事件（可选）
}
```

**失败时** (`success: False`):

```python
{"success": False, "text": "不知道'xxx'是什么呢……", "stats": {}, "image_needed": False}
```

---

### 2. 玩耍 `play(activity_id)`

```python
result = await diana.play(activity_id: str) -> dict
```

**参数**: `activity_id` — 活动 ID，见 [玩耍类](#2-玩耍类-play)

返回值结构同 `feed()`。

---

### 3. 打工 `work(work_id)`

```python
result = await diana.work(work_id: str) -> dict
```

**参数**: `work_id` — 工作 ID，见 [工作/直播类](#3-工作直播类-work)

返回值结构同 `feed()`。

---

### 4. 社交 `social(action_id)`

```python
result = await diana.social(action_id: str) -> dict
```

**参数**: `action_id` — 社交动作 ID，见 [社交/互动类](#4-社交互动类-social)

返回值结构同 `feed()`。

---

### 5. 日常 `daily(action_id)`

```python
result = await diana.daily(action_id: str) -> dict
```

**参数**: `action_id` — 日常活动 ID，见 [日常类](#5-日常类-daily)

返回值结构同 `feed()`。

---

### 6. 聊天 `talk(message)`

```python
result = await diana.talk(message: str) -> dict
```

**参数**: `message` — 用户发送的任意文本，自动检测关键词触发 meme 事件

**返回值**:

```python
{
    "text": "今天天气真好呢~",          # 回复文本
    "meme_triggered": False,           # 是否触发了梗事件
    "events": [],                      # 触发的事件列表
    "image": b"..." or None,           # 事件卡片图片（有事件时）
    "stats": { ... }                   # 当前属性
}
```

**触发 meme 事件时**:

```python
{
    "text": "🙏 嘉门！",               # 事件文本
    "meme_triggered": True,
    "events": [
        {"id": "嘉门", "type": "meme", "text": "🙏 嘉门！", "effects": {...}}
    ],
    "image": b"...",                  # 事件卡片图片
    "stats": { ... }
}
```

**支持的关键词**（25 个）: `嘉门`、`鸡胸肉`、`一米八`、`笑死`、`猫中毒`、`好耶`、`圣嘉然`、`小草莓`、`粉色矮子`、`嘉心糖屁用没有`、`打嗝`、`你画我猜`、`Mua`、`螺蛳粉`、`辣子鸡`、`连连看`、`宅舞20连`、`健身环`、`可颂`、`煎饺`、`JOJO`、`蟹炒年糕`、`土味情话`、`抱枕`、`生日`

---

### 7. 状态查看 `status()`

```python
result = await diana.status() -> dict
```

**返回值**:

```python
{
    "text": "🍽️ 饱腹度：80/100\n😊 心情：70/100\n...",  # 状态文本
    "image": b"...",                                   # 状态卡片 PNG
    "stats": { ... },                                  # 当前属性
    "alerts": "然然肚子好饿……🍗" or None                # 低属性警告
}
```

`alerts` 触发条件: 饱腹 <= 20、心情 <= 20、体力 <= 15、亲密度 <= 20

---

### 8. 时间流逝 `tick()`

```python
result = await diana.tick() -> dict
```

触发一次时间检查，包括属性衰减、随机事件、特殊日期事件、成就检查。

```python
{
    "events": [ ... ],           # 触发的事件列表
    "event_texts": ["..."],      # 事件文本列表（与 events 对应）
    "images": [b"...", ...],     # 事件卡片图片列表（与 events 一一对应）
    "stats": { ... }             # 当前属性
}
```

> 一般情况下不需要手动调用 `tick()`，`feed/play/work/social/daily/talk/status` 内部会自动调用 `tick()` 应用时间衰减。

---

### 9. 服装列表 `list_costumes()`

```python
costumes = diana.list_costumes() -> list[dict]
```

**返回值**（同步方法，不需要 await）:

```python
[
    {
        "id": "default",
        "name": "常服",
        "emoji": "👗",
        "description": "嘉然最经典的粉色日常服装...",
        "image": "default.png",
        "owned": True,       # 是否已解锁
        "equipped": True,    # 是否当前装备
        "unlock": {"type": "default"}
    },
    {
        "id": "tuantu",
        "name": "A-SOUL团服",
        "emoji": "🎤",
        "description": "A-SOUL团体演出服...",
        "image": "tuantu.png",
        "owned": False,
        "equipped": False,
        "unlock": {"type": "level", "value": 5}
    },
    # ...
]
```

---

### 10. 切换服装 `change_outfit(costume_id)`

```python
result = await diana.change_outfit(costume_id: str) -> dict
```

```python
# 成功
{"success": True, "text": "🎤 换上了「A-SOUL团服」！"}
# 失败（未解锁）
{"success": False, "text": "还没有解锁这件服装哦~"}
# 失败（不存在）
{"success": False, "text": "没有'xxx'这件服装呢……"}
```

---

### 11. 购买/解锁服装 `buy_costume(costume_id)`

```python
result = await diana.buy_costume(costume_id: str) -> dict
```

```python
# 成功
{"success": True, "text": "🧧 解锁了新服装「春节服」！"}
# 失败（条件不足）
{"success": False, "text": "需要 200 嘉心糖币"}
# 失败（已拥有）
{"success": False, "text": "已经拥有这件服装了~"}
```

---

### 12. 随机换装 `random_change_outfit()`

```python
result = await diana.random_change_outfit() -> dict
```

从已解锁服装中随机选一套（排除当前装备的），切换并返回结果。

```python
{"success": True, "text": "🐰 换上了「兔兔睡衣」！"}
```

---

### 13. 服装列表卡片 `costume_list_card()`

```python
img_bytes = await diana.costume_list_card() -> bytes
```

返回服装选择列表的 PNG 图片字节，展示所有服装的解锁状态和立绘。

---

### 14. 列出可用物品 `list_items(category=None)`

```python
items = diana.list_items(category: Optional[str] = None) -> list[dict]
```

**参数**: `category` — 可选筛选: `"food"`, `"play"`, `"work"`, `"social"`, `"daily"`；不传则返回全部

**返回值**（同步方法）:

```python
[
    {"id": "鸡胸肉", "category": "food", "description": "「半吊子的鸡胸肉」——感动了千万嘉心糖", "emoji": "🍗", "cost": 12},
    {"id": "薯片", "category": "food", "description": "嘉然最爱的薯片，嘎嘣脆", "emoji": "🍟", "cost": 8},
    # ...
]
```

---

### 15. 获取属性 `get_stats()`

```python
stats = diana.get_stats() -> dict
```

**返回值**（同步方法）:

```python
{
    "hunger": 80, "mood": 70, "energy": 90, "closeness": 50,
    "level": 1, "exp": 0, "coins": 100,
    "title": "新来的嘉心糖",
    "streak_days": 3,
    "outfit": "default",
    "owned_outfits": ["default", "tuantu"]
}
```

---

### 16. 设置用户生日 `set_user_birthday(birthday)`

```python
diana.set_user_birthday(birthday: str)
```

**参数**: `birthday` — 格式 `"MM-DD"`，如 `"08-15"`。当天执行 `talk()` 或 `tick()` 时会触发生日特殊事件。

---

### 17. 关闭实例 `close()`

```python
await diana.close()
```

保存当前状态到磁盘。**不关闭共享资源**（浏览器等由 `shutdown()` 统一管理）。

---

### 18. 进程退出清理 `shutdown()`

```python
from diana.api import shutdown
await shutdown()
```

关闭共享的 Chromium 浏览器实例。**在 Bot 进程退出时调用一次即可**。

---

## 物品/动作 ID 列表

### 1. 食物类 (food)

| ID | emoji | 饱腹 | 心情 | 体力 | 亲密度 | 金币 | 说明 |
|----|-------|------|------|------|--------|------|------|
| 薯片 | 🍟 | +15 | +5 | 0 | +2 | -8 | 嘎嘣脆 |
| 可乐 | 🥤 | +5 | +8 | 0 | +2 | -5 | 快乐水 |
| 鸡胸肉 | 🍗 | +25 | +15 | +5 | +8 | -12 | 经典名场面 |
| 小草莓 | 🍓 | +10 | +15 | 0 | +10 | -15 | 最甜甜甜的小草莓 |
| 螺蛳粉 | 🍜 | +30 | +8 | 0 | +3 | -10 | 然然最爱 |
| 抹茶零食 | 🍵 | +12 | +12 | 0 | +5 | -12 | 抹茶控 |
| 辣子鸡 | 🌶️ | +20 | **-15** | 0 | +2 | -10 | 被辣哭了！ |
| 煎饺 | 🥟 | +18 | +10 | 0 | +5 | -8 | 小巷美食 |
| 脆油条 | 🥖 | +15 | +5 | 0 | +3 | -5 | 小巷美食 |
| 烤串 | 🍢 | +22 | +10 | 0 | +4 | -15 | 吃遍大江南北 |
| 可颂 | 🥐 | +18 | +8 | 0 | +5 | -10 | 小巷美食 |
| 蟹炒年糕 | 🦀 | +28 | +12 | +5 | +6 | -18 | 名菜 |
| 汤年糕 | 🍲 | +20 | +10 | +5 | +4 | -10 | 冬日暖食 |
| 芋泥欧包 | 🍞 | +16 | +15 | 0 | +5 | -12 | 幸福感 |
| 生日蛋糕 | 🎂 | +10 | +30 | 0 | +15 | -30 | 生日限定 |
| 冰淇淋 | 🍦 | +8 | +15 | 0 | +5 | -6 | 夏日清凉 |
| 汉堡炸鸡 | 🍔 | +25 | +5 | 0 | 0 | -20 | 垃圾食品大餐 |
| 嘉心糖投喂自己 | 🍬 | **-10** | +25 | 0 | +12 | 0 | 整活专用 |
| 抹茶蛋糕 | 🍰 | +14 | +18 | 0 | +8 | -15 | 然然超爱 |
| 奶茶 | 🧋 | +8 | +12 | +5 | +5 | -12 | 暖暖的 |
| 提拉米苏 | 🍫 | +15 | +20 | 0 | +10 | -18 | 精致甜点 |

### 2. 玩耍类 (play)

| ID | emoji | 饱腹 | 心情 | 体力 | 亲密度 | 金币 | 说明 |
|----|-------|------|------|------|--------|------|------|
| 连连看 | 🎮 | -5 | +15 | -15 | +5 | 0 | 玩到凌晨5点 |
| 宅舞一支 | 💃 | -8 | +12 | -20 | +8 | 0 | 日常练舞 |
| 宅舞20连 | 🔥 | -15 | +25 | **-40** | +15 | **+30** | 名场面！ |
| 你画我猜 | 🎨 | -3 | +20 | -8 | +10 | 0 | Mua你一下~ |
| 糖豆人 | 🎯 | -5 | +15 | -10 | +5 | 0 | 联动游戏 |
| 健身环 | 🏋️ | -10 | **-10** | **-30** | +5 | 0 | 低气压警告 |
| JOJO立 | ⭐ | 0 | +18 | -10 | +8 | 0 | 整活时刻 |
| Switch游戏 | 🎲 | -5 | +18 | -10 | +8 | 0 | 任天堂毒唯 |
| 唱猫中毒 | 🐱 | -3 | +20 | -8 | +10 | +5 | 千万播放 |
| 唱YOU&IDOL | 🎤 | -3 | +15 | -5 | +8 | 0 | 精修翻唱 |
| 打嗝 | 😳 | 0 | **-15** | 0 | +10 | 0 | 偶像包袱爆炸 |
| 拍摄抖音 | 📱 | -3 | +10 | -8 | +5 | +10 | 短视频营业 |

### 3. 工作/直播类 (work)

| ID | emoji | 饱腹 | 心情 | 体力 | 亲密度 | 金币 | 说明 |
|----|-------|------|------|------|--------|------|------|
| 日常直播 | 📺 | -10 | 0 | -25 | +5 | +40 | B站日常 |
| 生日会直播 | 🎉 | -15 | +20 | -30 | +10 | **+100** | 年度盛典 |
| 练舞排练 | 🩰 | -8 | -5 | -20 | +3 | +10 | 挥洒汗水 |
| 团播 | 🌟 | -10 | +10 | -20 | +5 | +50 | A-SOUL全员 |
| 小剧场 | 🎭 | -5 | +15 | -15 | +8 | +30 | 搞活放松 |

### 4. 社交/互动类 (social)

| ID | emoji | 饱腹 | 心情 | 体力 | 亲密度 | 金币 | 说明 |
|----|-------|------|------|------|--------|------|------|
| 摸摸头 | ✋ | 0 | +10 | 0 | +12 | 0 | 摸呆毛~ |
| 说好耶 | 🎊 | 0 | +8 | 0 | +5 | 0 | 然然口头禅 |
| 喊一米八 | 📏 | 0 | **随机±15** | 0 | +3 | 0 | 身高梗 |
| 叫嘉门 | 🙏 | 0 | +15 | 0 | +8 | +5 | 圣嘉然模式 |
| 叫粉色矮子 | 💢 | 0 | **-20** | 0 | **-5** | 0 | 踩雷！！ |
| 说嘉心糖屁用没有 | 😢 | 0 | -10 | 0 | +5 | 0 | 反向激将 |
| 写信小作文 | ✉️ | 0 | +20 | 0 | +15 | +10 | 真情流露 |
| 送抱枕 | 🎁 | 0 | +15 | 0 | +15 | **-25** | 礼物 |
| Mua | 💋 | 0 | +25 | 0 | +20 | 0 | 经典互动 |
| 说土味情话 | 💌 | 0 | +10 | 0 | +5 | 0 | 嘉然喜欢 |

### 5. 日常类 (daily)

| ID | emoji | 饱腹 | 心情 | 体力 | 亲密度 | 金币 | 说明 |
|----|-------|------|------|------|--------|------|------|
| 休息 | 😴 | 0 | -5 | **+30** | 0 | 0 | 恢复体力 |
| 逛街 | 🛍️ | -5 | +15 | -15 | +8 | **-20** | 小巷觅食 |
| 上学 | 📚 | -5 | -5 | -10 | 0 | +15 | 枝江大学 |
| 换装 | 👗 | 0 | +10 | 0 | +5 | **-30** | 触发随机换装 |
| 自画像 | 🖼️ | 0 | +10 | -5 | +10 | 0 | 给糖糖画画像 |
| 敷面膜 | 💆 | 0 | +10 | +5 | +3 | -10 | 偶像保养 |
| 刷B站 | 📱 | 0 | +10 | -5 | 0 | 0 | 看二创 |
| 吃夜宵 | 🌙 | +15 | +10 | 0 | +3 | -10 | 深夜放毒 |

> `喊一米八` 的心情变化是随机的: -15 / -10 / -5 / +5 / +10 / +15，各 1/6 概率。
>
> `换装` 动作执行时会自动触发一次随机换装（从已解锁的非当前服装中随机选一套）。

---

## 服装系统

### 服装列表

| ID | 名称 | emoji | 解锁条件 |
|----|------|-------|----------|
| `default` | 常服 | 👗 | 初始拥有 |
| `tuantu` | A-SOUL团服 | 🎤 | 等级达到 5 |
| `yongzhuang` | 泳装 | 🏖️ | 等级达到 10 |
| `chunjie` | 春节服 | 🧧 | 花费 200 嘉心糖币购买 |
| `shuiyi` | 兔兔睡衣 | 🐰 | 达成成就「连续互动7天」 |

### 自动解锁

等级提升时会自动检查并解锁对应等级要求的服装（`tuantu` / `yongzhuang`），无需手动调用 `buy_costume()`。

### 服装立绘

每套服装对应 `assets/images/costumes/{id}.png`（500x500 透明背景），渲染 status_card 时自动嵌入右侧。

---

## 事件系统

### 事件类型

| 类型 | 说明 | 触发方式 |
|------|------|----------|
| `random` | 30 个随机事件 | `tick()` 中按概率触发（1-5%） |
| `meme` | 25 个梗事件 | `talk()` 中关键词检测触发 |
| `special_date` | 15 个特殊日期 | `tick()` 中日期匹配触发（如 03-07 嘉然生日周） |
| `achievement` | 10 个成就 | `tick()` 中条件满足时触发 |

### 成就列表

| 成就 | 条件 |
|------|------|
| 连续互动7天 | `streak_days >= 7` |
| 连续互动30天 | `streak_days >= 30` |
| 亲密度达到100 | `closeness >= 100` |
| 等级达到10 | `level >= 10` |
| 等级达到20 | `level >= 20` |
| 喂食100次 | `interaction_feed_count >= 100` |
| 玩耍100次 | `interaction_play_count >= 100` |
| 触发10个meme | `meme_triggers_count >= 10` |
| 嘉然生日当天 | 03-07 当天触发 |
| 解锁全部服装 | 拥有 5 套服装 |

### 梗关键词 (25个)

`嘉门` `鸡胸肉` `一米八` `笑死` `猫中毒` `好耶` `圣嘉然` `小草莓` `粉色矮子` `嘉心糖屁用没有` `打嗝` `你画我猜` `Mua` `螺蛳粉` `辣子鸡` `连连看` `宅舞20连` `健身环` `可颂` `煎饺` `JOJO` `蟹炒年糕` `土味情话` `抱枕` `生日`

---

## 对话系统

- 对话按 `{category}_{action_id}` 匹配，存储在 `data/dialogues.yaml`（250+ 条）
- 加权随机选择，同一用户最近 5 条不重复
- 共享的 `InteractionService` 确保对话历史在进程内跨请求持久化
- 未匹配到对话时使用 fallback 通用对话
- `talk()` 未触发事件时返回 `idle` 闲谈对话

---

## 属性与升级

### 属性范围与衰减

| 属性 | 范围 | 衰减速率 | 归零惩罚 |
|------|------|----------|----------|
| 饱腹 (hunger) | 0-100 | -2.5/h | 额外扣心情 10 |
| 心情 (mood) | 0-100 | -2/h | — |
| 体力 (energy) | 0-100 | -1/h | — |
| 亲密度 (closeness) | 0-100 | -3/天（未互动） | — |

### 低属性警告阈值

- 饱腹 <= 20: 饥饿警告
- 心情 <= 20: 低落警告
- 体力 <= 15: 疲惫警告
- 亲密度 <= 20: 疏远警告

### 等级与称号

| 等级 | 称号 |
|------|------|
| 1 | 新来的嘉心糖 |
| 3 | 小草莓 |
| 5 | 小草莓守护者 |
| 7 | 糖糖糖 |
| 10 | 嘉门传教士 |
| 13 | 然然的好朋友 |
| 16 | 宅舞练习生 |
| 20 | 圣嘉然骑士 |
| 25 | 嘉心糖大将军 |
| 30 | 最好的嘉心糖 |

每 100 经验升 1 级，升级时自动更新称号。经验来自: `closeness 增量 × 2`。

### 连续互动天数

- 每日至少一次互动（feed/play/work/social/daily 任意一种）
- 连续天数递增，中断则重置为 0
- 中断时亲密度 -3

---

## 错误处理

所有方法都不会抛出异常（Playwright 渲染错误除外）。业务错误通过 `success: False` 返回：

```python
result = await diana.feed("不存在的食物")
# {"success": False, "text": "不知道'不存在的食物'是什么呢……", "stats": {}, "image_needed": False}

result = await diana.buy_costume("chunjie")
# {"success": False, "text": "需要 200 嘉心糖币"}  -- 金币不足

result = await diana.change_outfit("chunjie")
# {"success": False, "text": "还没有解锁这件服装哦~"}  -- 未解锁
```

**渲染异常（已内置降级）**: 所有 render 调用（`render_status_card` / `render_interaction_card` / `render_event_card` / `render_costume_list`）都被 `try/except Exception` 包裹。Playwright Chromium 崩溃、模板渲染失败、Jinja2 语法错误等情况会**写 WARNING 日志并把 `result["image"]` 置为 `None`**，业务数据（属性变化、对话、save 落盘）照常完成。Bot 插件层只需在发送时判空即可：

```python
if result.get("image") is not None:
    await send_image(result["image"])
await send_text(result["text"])
```

**存档版本迁移**: `utils._migrate_save()` 在 `load_pet()` 时自动把缺 `version` 字段的旧存档补为 `0`，下次 `_save()` 由 `to_dict()` 写入 `SAVE_VERSION`。`SAVE_VERSION` 常量在 `diana/utils.py` 顶部，新增字段时递增并在该函数中追加迁移分支。详见"数据存储"章节。

---

## NoneBot 插件实现

### 项目结构

```
your-nonebot-project/
├── pyproject.toml / bot.py            # NoneBot 入口
└── src/plugins/
    └── diana_pet/
        ├── __init__.py                 # 插件注册 + 所有 matcher
        └── data/                       # 可选：指向 Diana_pet/data/ 的 symlink
```

### 完整插件代码 (`__init__.py`)

```python
"""
NoneBot 嘉然宠物插件 — DianaPet for NoneBot2.

指令:
  然然状态           - 查看状态卡片
  然然衣柜           - 服装列表卡片
  喂食 / 吃 <食物>   - 喂食
  玩 / 玩耍 <活动>   - 和然然玩
  打工 / 直播 <工作> - 然然打工
  摸摸头 / 好耶 / 嘉门 / Mua / ...  - 社交互动
  休息 / 逛街 / 上学 / ...           - 日常活动
  换装 <服装名>      - 切换服装 (不指定则随机)
  解锁 <服装名>      - 购买/解锁服装
  然然 <任意文本>    - 聊天（关键词触发梗事件）
"""

import re
import asyncio
from pathlib import Path
from typing import Optional

from nonebot import on_command, on_message, on_keyword, require
from nonebot.adapters.onebot.v11 import Bot, Event, Message, MessageSegment
from nonebot.matcher import Matcher
from nonebot.params import CommandArg, EventPlainText
from nonebot.plugin import PluginMetadata
from nonebot.message import run_preprocessor, event_preprocessor

from diana.api import DianaPet, shutdown

__plugin_meta__ = PluginMetadata(
    name="嘉然宠物",
    description="嘉然 Diana 虚拟宠物养成系统",
    usage="然然状态 / 喂食鸡胸肉 / 玩连连看 / 摸摸头 / 打工日常直播 / ...",
    extra={"author": "DianaPet", "version": "0.1.0"},
)

# ── 路径配置（指向 Diana_pet 项目目录）──
DIANA_DATA_DIR = Path(__file__).parent.parent.parent / "data"
DIANA_ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"
DIANA_SAVES_DIR = Path(__file__).parent / "saves"  # 存档放插件目录下

USER_CACHE: dict[str, DianaPet] = {}
CACHE_MAX_SIZE = 500  # 最多缓存 500 个用户


def get_user_id(event: Event) -> str:
    """从事件中提取用户唯一标识."""
    return str(event.get_user_id())


async def get_diana(user_id: str) -> DianaPet:
    """获取或创建 DianaPet 实例，LRU 淘汰."""
    if user_id not in USER_CACHE:
        if len(USER_CACHE) >= CACHE_MAX_SIZE:
            oldest = next(iter(USER_CACHE))
            await USER_CACHE.pop(oldest).close()
        USER_CACHE[user_id] = DianaPet(
            user_id, DIANA_DATA_DIR, DIANA_ASSETS_DIR, DIANA_SAVES_DIR,
        )
    return USER_CACHE[user_id]


async def send_result(
    bot: Bot, event: Event, result: dict, matcher: Optional[Matcher] = None
):
    """将 DianaPet API 返回结果发送给用户."""
    text = result.get("text", "")
    image = result.get("image")

    if image:
        # 先发图片再发文字
        if matcher:
            await matcher.send(MessageSegment.image(image))
        if text:
            if matcher:
                await matcher.send(text)
    else:
        if text:
            if matcher:
                await matcher.send(text)


# ── 生命周期 ──

from nonebot import get_driver

driver = get_driver()


@driver.on_shutdown
async def _shutdown():
    for diana in USER_CACHE.values():
        await diana.close()
    await shutdown()


# ============================================================
# Matcher 1: 状态卡片
# ============================================================
status_cmd = on_command("然然状态", aliases={"状态", "我的然然", "然然信息"})


@status_cmd.handle()
async def handle_status(bot: Bot, event: Event, matcher: Matcher):
    diana = await get_diana(get_user_id(event))
    result = await diana.status()
    await send_result(bot, event, result, matcher)


# ============================================================
# Matcher 2: 衣柜
# ============================================================
wardrobe_cmd = on_command("然然衣柜", aliases={"服装", "衣柜", "换装列表"})


@wardrobe_cmd.handle()
async def handle_wardrobe(bot: Bot, event: Event, matcher: Matcher):
    diana = await get_diana(get_user_id(event))
    img = await diana.costume_list_card()
    await matcher.send("🎀 然然的衣柜：")
    await matcher.send(MessageSegment.image(img))


# ============================================================
# Matcher 3: 喂食（精确匹配物品名）
# ============================================================
# 先用一个统一的 on_message 做指令解析，再用 on_keyword 做社交/日常

food_cmd = on_command("喂食", aliases={"喂", "吃", "投喂"}, block=False)


@food_cmd.handle()
async def handle_feed(
    bot: Bot, event: Event, matcher: Matcher, args: Message = CommandArg()
):
    food_name = args.extract_plain_text().strip()
    if not food_name:
        await matcher.finish("要吃什么呢？比如：吃鸡胸肉、吃小草莓、吃薯片……")
    diana = await get_diana(get_user_id(event))
    result = await diana.feed(food_name)
    await send_result(bot, event, result, matcher)


# ============================================================
# Matcher 4: 玩耍
# ============================================================
play_cmd = on_command("玩耍", aliases={"玩"}, block=False)


@play_cmd.handle()
async def handle_play(
    bot: Bot, event: Event, matcher: Matcher, args: Message = CommandArg()
):
    activity = args.extract_plain_text().strip()
    if not activity:
        await matcher.finish(
            "玩什么呢？比如：玩连连看、玩宅舞一支、玩你画我猜、玩糖豆人……"
        )
    diana = await get_diana(get_user_id(event))
    result = await diana.play(activity)
    await send_result(bot, event, result, matcher)


# ============================================================
# Matcher 5: 打工
# ============================================================
work_cmd = on_command("打工", aliases={"直播", "工作"}, block=False)


@work_cmd.handle()
async def handle_work(
    bot: Bot, event: Event, matcher: Matcher, args: Message = CommandArg()
):
    work_name = args.extract_plain_text().strip()
    if not work_name:
        await matcher.finish(
            "做什么工作呢？比如：打工日常直播、打工生日会直播、打工团播……"
        )
    diana = await get_diana(get_user_id(event))
    result = await diana.work(work_name)
    await send_result(bot, event, result, matcher)


# ============================================================
# Matcher 6: 换装
# ============================================================
costume_cmd = on_command("换装", aliases={"换上", "穿"})


@costume_cmd.handle()
async def handle_costume(
    bot: Bot, event: Event, matcher: Matcher, args: Message = CommandArg()
):
    costume_name = args.extract_plain_text().strip()
    diana = await get_diana(get_user_id(event))

    if costume_name:
        # 按名称匹配服装 ID
        costumes = diana.list_costumes()
        matched = None
        for c in costumes:
            if c["name"] in costume_name or costume_name in c["name"]:
                matched = c
                break
        if matched:
            result = await diana.change_outfit(matched["id"])
        else:
            result = {"success": False, "text": f"没有找到'{costume_name}'这件服装呢……"}
    else:
        # 随机换装
        result = await diana.random_change_outfit()

    await send_result(bot, event, result, matcher)


# ============================================================
# Matcher 7: 解锁服装
# ============================================================
unlock_cmd = on_command("解锁", aliases={"购买"})


@unlock_cmd.handle()
async def handle_unlock(
    bot: Bot, event: Event, matcher: Matcher, args: Message = CommandArg()
):
    costume_name = args.extract_plain_text().strip()
    diana = await get_diana(get_user_id(event))

    if not costume_name:
        # 列出可解锁的服装
        costumes = diana.list_costumes()
        locked = [c for c in costumes if not c["owned"]]
        if locked:
            lines = ["可解锁的服装："]
            for c in locked:
                unlock = c["unlock"]
                utype = unlock.get("type", "")
                uvalue = unlock.get("value", "")
                if utype == "level":
                    cond = f"需要 Lv.{uvalue}"
                elif utype == "coins":
                    cond = f"需要 {uvalue} 嘉心糖币"
                elif utype == "achievement":
                    cond = "成就解锁"
                else:
                    cond = "特殊条件"
                lines.append(f"  {c['emoji']} {c['name']} — {cond}")
            await matcher.finish("\n".join(lines))
        else:
            await matcher.finish("你已经解锁了全部服装！")
        return

    # 按名称匹配
    costumes = diana.list_costumes()
    matched = None
    for c in costumes:
        if c["name"] in costume_name or costume_name in c["name"]:
            matched = c
            break
    if matched:
        result = await diana.buy_costume(matched["id"])
    else:
        result = {"success": False, "text": f"没有找到'{costume_name}'这件服装呢……"}

    await send_result(bot, event, result, matcher)


# ============================================================
# Matcher 8: 社交互动（关键词触发）
# ============================================================
SOCIAL_KEYWORDS = {
    "摸摸头": "摸摸头",
    "摸头": "摸摸头",
    "好耶": "说好耶",
    "一米八": "喊一米八",
    "嘉门": "叫嘉门",
    "粉色矮子": "叫粉色矮子",
    "屁用没有": "说嘉心糖屁用没有",
    "嘉心糖屁用没有": "说嘉心糖屁用没有",
    "小作文": "写信小作文",
    "写信": "写信小作文",
    "抱枕": "送抱枕",
    "mua": "Mua",
    "Mua": "Mua",
    "土味情话": "说土味情话",
    "情话": "说土味情话",
}

# 为每个社交关键词注册一个独立的 on_keyword matcher
for kw, action_id in SOCIAL_KEYWORDS.items():
    # 避免重复注册和名称冲突
    kw_matcher = on_keyword({kw}, rule=None)

    # 用闭包捕获 action_id
    def _make_handler(aid):
        async def _handler(bot: Bot, event: Event, matcher: Matcher):
            diana = await get_diana(get_user_id(event))
            result = await diana.social(aid)
            await send_result(bot, event, result, matcher)

        return _handler

    kw_matcher.handle()(_make_handler(action_id))


# ============================================================
# Matcher 9: 日常活动（关键词触发）
# ============================================================
DAILY_MAP = {
    "休息": "休息",
    "逛街": "逛街",
    "上学": "上学",
    "自画像": "自画像",
    "敷面膜": "敷面膜",
    "刷B站": "刷B站",
    "刷b站": "刷B站",
    "夜宵": "吃夜宵",
    "吃夜宵": "吃夜宵",
}

for kw, action_id in DAILY_MAP.items():
    kw_matcher = on_keyword({kw})

    def _make_daily_handler(aid):
        async def _handler(bot: Bot, event: Event, matcher: Matcher):
            diana = await get_diana(get_user_id(event))
            result = await diana.daily(aid)
            await send_result(bot, event, result, matcher)

        return _handler

    kw_matcher.handle()(_make_daily_handler(action_id))


# ============================================================
# Matcher 10: 聊天（兜底，最低优先级）
# ============================================================
# 当用户消息以 "然然" 开头或包含 "@然然" 时，进入聊天模式
talk_cmd = on_command("然然", aliases={"然然聊天"}, block=False)


@talk_cmd.handle()
async def handle_talk(
    bot: Bot, event: Event, matcher: Matcher, args: Message = CommandArg()
):
    text = args.extract_plain_text().strip()
    diana = await get_diana(get_user_id(event))
    result = await diana.talk(text)
    await send_result(bot, event, result, matcher)


# ============================================================
# Matcher 11: 帮助
# ============================================================
help_cmd = on_command("然然帮助", aliases={"宠物帮助", "然然指令"})


@help_cmd.handle()
async def handle_help(matcher: Matcher):
    help_text = """
🍓 **嘉然 Diana 宠物养成系统** 🍓

**查看状态**
  然然状态 — 查看然然当前状态卡片
  然然衣柜 — 查看服装收集情况

**喂食** (21种)
  吃鸡胸肉 / 吃小草莓 / 吃螺蛳粉 / 吃薯片 / 吃生日蛋糕 / ...

**玩耍** (12种)
  玩连连看 / 玩宅舞一支 / 玩宅舞20连 / 玩你画我猜 / 玩Switch游戏 / ...

**打工** (5种)
  打工日常直播 / 打工生日会直播 / 打工团播 / 练舞排练 / 小剧场

**互动** (10种, 社交类)
  互动 摸摸头 / 互动 Mua / 互动 喊一米八 / 互动 叫嘉门 / 互动 送抱枕 / ...
  （YAML 内部 category 仍为 social）

**日常** (8种)
  日常 休息 / 日常 逛街 / 日常 刷B站 / 日常 吃夜宵 / ...

**换装**
  换装 — 随机换装
  换装 团服 / 换装 泳装 / ... — 切换指定服装
  解锁 春节服 / 解锁 兔兔睡衣 — 购买/解锁服装

**聊天**
  然然 <你想说的话> — 和然然聊天（自动触发梗事件）

🔗 项目: Diana_pet
"""
    await matcher.send(help_text.strip())
```

### 依赖配置 (`pyproject.toml`)

```toml
[project]
name = "diana-pet-bot"
version = "0.1.0"

[tool.nonebot]
plugins = ["diana_pet"]
adapters = [
    { name = "OneBot V11", module_name = "nonebot.adapters.onebot.v11" },
]
```

### 目录要求

插件需要能访问 `diana/` 包和 `data/` 目录。推荐两种方式：

**方式 A**: 直接把 `Diana_pet` 目录放到 Bot 项目同级，修改 `PYTHONPATH`：

```bash
PYTHONPATH=/path/to/Diana_pet:$PYTHONPATH nb run
```

**方式 B**: 在 Bot 项目的 `requirements.txt` 中加入 DianaPet 的路径依赖，`data_dir` 参数指向正确路径。

---

## AI 实现指南（NoneBot）

当你让 AI 基于本文档实现 NoneBot 插件时，请确保以下几点：

### 必须遵守

1. **`DianaPet` 实例绑定用户**: 每个 QQ 号一个实例，用 `dict[user_id, DianaPet]` 缓存。建议 LRU 淘汰，最多缓存 500 个用户，超过则移除最旧的
2. **首次构造指定三个路径**: `DianaPet(user_id, data_dir, assets_dir, saves_dir)` 首次调用时指定所有目录，后续实例的路径参数会被忽略（共享服务已初始化）
3. **服务自动共享**: 不需要手动管理 `InteractionService` / `EventManager` / `Renderer`，`DianaPet.__init__` 自动从模块级共享池获取
4. **返回值始终检查 `success`**: `success: False` 时 `image` 为 `None`，只用 `matcher.send(text)` 发文本
5. **进程退出调用 `shutdown()`**: 在 `@driver.on_shutdown` 中调用，否则 Chromium 进程残留
6. **NoneBot 异步**: 所有 DianaPet 方法都是 `async`，matcher handler 中直接 `await` 即可

### 路径配置

```python
from pathlib import Path

# data_dir: YAML 配置 + Jinja2 模板
# assets_dir: 服装立绘 PNG
# saves_dir: 用户存档 JSON
DIANA = Path("/path/to/Diana_pet")
diana = DianaPet(
    user_id,
    data_dir=DIANA / "data",
    assets_dir=DIANA / "assets",
    saves_dir=Path("./saves"),  # 可独立于项目目录
)
```

三个目录均可独立指定，`saves_dir` 推荐放在 Bot 插件自己的目录下方便持久化。

### NoneBot2 关键对象

| 对象 | 用途 |
|------|------|
| `get_user_id(event: Event) -> str` | 获取 QQ 号作为 user_id |
| `MessageSegment.image(image_bytes)` | 构造图片消息段 |
| `matcher.send(msg)` | 发送消息 |
| `matcher.finish(msg)` | 发送并结束当前 matcher |
| `CommandArg()` | 获取指令参数 |
| `@driver.on_shutdown` | 注册关闭钩子 |

### 建议实现

6. **模糊匹配物品名**: 用户可能打错字（"鸡胸"→"鸡胸肉"、"连连"→"连连看"），用 `in` 做子串匹配
7. **输入为空时提示**: 当 `CommandArg` 为空时，返回该类别可用物品列表作为提示
8. **帮助菜单**: 实现 `然然帮助` 列出所有指令
9. **互动/日常动作用 `on_command`**: 本仓库当前实现为 `on_command("互动", ...)` / `on_command("日常", ...)`，与本节描述的"`on_keyword` 关键词触发"不同；YAML 内部 category 仍为 `social` / `daily`，但用户面向层用"互动"（"社交"用词不自然）。照搬本文档生成的代码请按当前实现选择命令风格。
10. **聊天用 `on_command("然然", ...)`**: 只有带"然然"前缀的消息才走聊天通道，避免过度触发

### 性能参考

| 场景 | 耗时 | 备注 |
|------|------|------|
| 无渲染操作 (list_items/get_stats) | < 1ms | 纯内存，极快 |
| JSON 读写 | ~5ms | 磁盘 I/O |
| PNG 渲染（单个） | 0.5-2s | 取决于 CPU，1C2G 约 1-2s |
| 首次启动（含 Chromium 启动） | 3-5s | 一次性开销 |
| Chromium 内存占用 | 300-500MB | 共享单例，只占一份 |
| 每增加一个并发渲染 | +50-100MB | 受 `MAX_CONCURRENT_RENDERS` 限制 |

### MAX_CONCURRENT_RENDERS 调整（重要！）

1C2G 服务器务必调低并发渲染数。在 `diana/api.py` 顶部：

```python
MAX_CONCURRENT_RENDERS = 1  # 1C2G 建议设为 1，高配服务器可调到 2-4
```

### Bot 启动配置示例

```bash
# 方式 1: 设置 PYTHONPATH
cd /path/to/your-bot
PYTHONPATH=/path/to/Diana_pet:$PYTHONPATH nb run

# 方式 2: 在 .env 中配置
echo 'PYTHONPATH=/path/to/Diana_pet' >> .env
```
