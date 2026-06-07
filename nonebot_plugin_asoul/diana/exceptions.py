"""Diana 宠物系统自定义异常.

所有业务错误通过这些异常抛出，api.py 层捕获后转为 {success: False, text: ...} 字典，
保持对外 API 不变。调用方无需感知异常层次。
"""


class DianaError(Exception):
    """Diana 宠物系统异常基类."""


class ActionNotFoundError(DianaError):
    """动作/物品 ID 不存在."""

    def __init__(self, action_id: str):
        self.action_id = action_id
        super().__init__(f"不知道'{action_id}'是什么呢……")


class InsufficientCoinsError(DianaError):
    """嘉心糖币不足."""

    def __init__(self):
        super().__init__("嘉心糖币不够了……让然然去打工会不会好一点？")


class CostumeLockedError(DianaError):
    """服装未解锁."""

    def __init__(self, reason: str = ""):
        self.reason = reason
        super().__init__(reason or "还没有解锁这件服装哦~")


class CostumeNotFoundError(DianaError):
    """服装 ID/名称不存在."""

    def __init__(self, costume_id: str):
        self.costume_id = costume_id
        super().__init__(f"没有'{costume_id}'这件服装呢……")