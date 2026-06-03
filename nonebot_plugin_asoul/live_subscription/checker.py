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
    """持有内存状态，负责状态比对和开播通知。"""

    def __init__(self, api: BiliLiveAPI, notifier: Notifier) -> None:
        self._api = api
        self._notifier = notifier
        self._state: dict[int, int] = {}   # uid → live_status (归一化: 0/1)
        self._meta: dict[int, LiveInfo] = {}  # uid → 上次的 LiveInfo

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
                    await self._notifier.on_live_start(info)
                else:
                    await self._notifier.on_live_stop(info, self._meta.get(uid))
                self._state[uid] = new_status
                self._meta[uid] = info

    async def close(self) -> None:
        await self._api.close()
