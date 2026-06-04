"""
@Author: star_482
@Date: 2026/6/4
@File: checker
@Description: 直播状态比对器。持有内存状态，检测 0→1（开播）变化并通知。
"""
from nonebot.log import logger

from .api import BiliLiveAPI, LiveInfo
from .notifier import Notifier


class LiveChecker:
    """持有内存状态，负责状态比对和开播通知。

    开播检测采用两阶段确认：
    1. 检测到 0→1 变化 → 标记 pending，暂不通知
    2. 下一次轮询仍为直播中 → 确认通知（此时 API 标题已刷新）
    避免轮播(2)→直播(1)切换时 API 标题字段缓存滞后导致通知携带旧标题。
    """

    def __init__(self, api: BiliLiveAPI, notifier: Notifier) -> None:
        self._api = api
        self._notifier = notifier
        self._state: dict[int, int] = {}     # uid → live_status (归一化: 0/1)
        self._meta: dict[int, LiveInfo] = {}  # uid → 上次的 LiveInfo
        self._pending: set[int] = set()       # 待确认开播的 uid（已检测到 0→1，等下次轮询确认）

    async def check(self, uids: list[int]) -> None:
        """执行一轮检查。首次记录不触发通知。"""
        results = await self._api.fetch_live_status(uids)

        for uid in uids:
            info = results.get(uid)
            if info is None:
                continue

            new_status = 1 if info.live_status == 1 else 0
            old_status = self._state.get(uid)

            if old_status is None:
                self._state[uid] = new_status
                self._meta[uid] = info
                logger.debug(
                    f"首次记录: {info.uname} (uid={uid}) status={new_status}"
                )
                continue

            if new_status != old_status:
                if new_status == 1:
                    # 0→1：标记为待确认，等下一轮 title 刷新后再通知
                    self._pending.add(uid)
                    logger.debug(
                        f"开播待确认: {info.uname} (uid={uid}), 当前标题: {info.title}"
                    )
                else:
                    # 1→0：下播，清除 pending 并通知
                    self._pending.discard(uid)
                    await self._notifier.on_live_stop(info, self._meta.get(uid))
                self._state[uid] = new_status
                self._meta[uid] = info
            elif new_status == 1 and uid in self._pending:
                # 上次已确认为待确认，本轮流仍为直播中 → 确认开播
                self._pending.discard(uid)
                self._meta[uid] = info
                await self._notifier.on_live_start(info)
                logger.info(f"开播确认: {info.uname} (uid={uid}), 标题: {info.title}")

    async def close(self) -> None:
        await self._api.close()
