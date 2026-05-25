# nonebot-plugin-asoul

面向 A-SOUL 及嘉然（Diana）粉丝的 NoneBot2 插件，提供发病小作文、每日运势、直播日程等功能，适配 QQ 官方机器人。

---

## 功能一览

### 常用指令

| 指令 | 别名 | 说明 |
| --- | --- | --- |
| `/发病小作文` | `/发病` | 随机发送一条嘉然相关的小作文 |
| `/今日运势` | `/抽签` | 每人每日一次，生成专属运势卡片图 |
| `/本周日程` | `/日程` | 查看今天与明天的安排，并附本周日程图 |
| `/关于小然` | `/小然`、`/关于然然` | 嘉然 & Bot 介绍（Markdown + 内联按钮） |
| `/抽老婆` | — | 随机抽取一张图片 |
| `/今天吃什么` | `今天/明天/早上/晚上吃什么` 等正则匹配 | 随机推荐一张菜品图 |
| `/今天喝什么` | 同上喝法 | 随机推荐一张饮品图 |
| `/我的id` | — | 查看自己在 QQ 官方机器人下的 openid |

### 嘉然宠物养成（开发中）

基于属性衰减 + 等级 + 服装解锁的轻量养成系统，目前处于开发阶段，指令与机制可能随时调整，暂不在此文档中详述。设计与 API 见 `nonebot_plugin_asoul/diana/API_REFERENCE.md`。

### 管理员（SUPERUSER）

- `/添加日程` — 发图片即更新本周日程图；发 JSON 文本即合并到 `activity.json`
- `/统计总览`、`/统计排行`、`/统计明细` — 查看插件命令使用情况

---

## 安装

本仓库是一个 NoneBot2 插件包，不包含运行时（无 `pyproject.toml`/`requirements.txt`），需要放入宿主 NoneBot 项目中使用。

### 1. 依赖

宿主项目需安装：

```bash
pip install nonebot2 nonebot-adapter-qq nonebot-plugin-alconna
pip install httpx pillow pyyaml jinja2 playwright
playwright install chromium
```

> `playwright + chromium` 仅在使用嘉然宠物相关图片渲染时需要。

### 2. 安装插件

将本仓库 `nonebot_plugin_asoul/` 目录放入宿主项目 `plugins/`，或在 `bot.py` 中加载：

```python
import nonebot
nonebot.load_plugin("nonebot_plugin_asoul")
```

### 3. 放置数据目录

将本仓库的 `data/` 目录复制到宿主项目的工作目录下。默认数据根为 `./data/asoul/`，主要内容：

```
data/
├── asoul/
│   ├── quotation.json            # 发病小作文（首次启动会自动下载）
│   ├── activity/                 # 周日程 (new_activity.jpg + activity.json)
│   ├── resource/
│   │   ├── font/                 # Mamelon.otf / sakura.ttf
│   │   ├── fortune/              # copywriting.json（首次启动前需就位）
│   │   ├── img/asoul/            # 抽签底图
│   │   └── out/                  # 抽签结果输出目录（自动创建）
│   ├── wife_img/                 # 抽老婆图片池
│   └── stats/                    # 命令统计（自动写入）
└── whateat_pic/
    ├── eat_pic/                  # 吃什么图片池
    └── drink_pic/                # 喝什么图片池
```

> ⚠ `whateat`（今天吃/喝什么）的图片目录写死为 `./data/whateat_pic`，相对启动时的工作目录，不受 `data_path` 配置影响。

---

## 配置项

在宿主项目 `.env` 中配置（或直接使用默认值）：

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `data_path` | `./data/asoul` | 数据根目录 |
| `wife_img_dir` | `wife_img` | 抽老婆图片子目录 |
| `command_priority` | `15` | 所有指令的统一优先级 |
| `home_url` | 上游仓库地址 | 关于页链接 |
| `whateat_cd` | `10` | 吃 / 喝什么的全局冷却（秒） |
| `whateat_max` | `0` | 每用户每日上限，`0` 表示不限 |

> 嘉然宠物相关配置（`diana_data_dir` / `diana_assets_dir` / `diana_saves_dir`）随该模块开发进展再行说明。

---

## 适配器与消息

- **目标适配器**：`nonebot.adapters.qq`（QQ 官方机器人）
- 部分处理器直接使用 `GroupAtMessageCreateEvent`，仅在 QQ 群 @ 机器人 时可触发
- 插件优先使用 QQ 适配器原生 `MessageSegment`（如 `MessageSegment.markdown()`、`MessageSegment.keyboard()`），以充分使用 QQ 官方机器人的能力；仅在确实需要跨适配器或额外段类型时使用 `nonebot_plugin_alconna.uniseg.UniMessage`。

---

## 项目结构

```
nonebot_plugin_asoul/
├── __init__.py          # 命令注册入口，通过 import 拉起各子模块
├── config.py            # Pydantic 插件配置
├── start_up.py          # on_startup 钩子：缺失的 quotation.json 自动下载
├── admin_stats.py       # 全局 pre/post processor 统计命令使用情况
├── activity.py          # 周日程读写
├── fortune_manager.py   # 抽签（每日每用户每群一次）
├── random_wife.py       # 抽老婆
├── markdown.py          # QQ Markdown + 内联键盘
├── whateat.py           # 今天吃/喝什么 (Alconna shortcut)
├── diana_pet.py         # 嘉然宠物接入层（开发中）
├── utils.py             # JSON 读写、图片下载、抽签合成
└── diana/               # 嘉然宠物核心，独立子包（开发中）
```

---

## 上游

主仓库（含资源文件初始模板）：
<https://github.com/whalefall123456/nonebot-plugin-asoul>
