"""
@Author: star_482
@Date: 2026/5/26
@File: r2_client
@Description: Cloudflare R2 (S3 兼容) 客户端单例。封装同步底层操作，由 R2Bucket 通过 to_thread 调用。
"""
from threading import Lock
from typing import Optional

from nonebot.log import logger

from ..config import config

_client = None
_lock = Lock()


def _build_client():
    """懒构造 boto3 S3 客户端。延迟导入 boto3，避免插件加载时强依赖未安装的依赖。

    兼容 Cloudflare R2 与腾讯云 COS：两者都走 S3 协议，差异仅在 endpoint / region。
    R2 用 region="auto"；COS 必须用实际区域（如 ap-guangzhou），否则 SigV4 签名校验失败。
    """
    import boto3
    from botocore.config import Config as BotoConfig

    return boto3.session.Session().client(
        service_name="s3",
        endpoint_url=config.r2_url,
        aws_access_key_id=config.r2_id,
        aws_secret_access_key=config.r2_key,
        region_name=config.r2_region,
        config=BotoConfig(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def get_client():
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = _build_client()
                logger.info("R2 客户端已初始化")
    return _client


def reset_client():
    """仅用于测试或凭据热重载。"""
    global _client
    with _lock:
        _client = None


# ── 同步底层操作（异常会上抛，由调用方 try/except 转为 None）──

def put_object_sync(key: str, data: bytes, content_type: str, metadata: dict | None = None):
    kwargs = dict(
        Bucket=config.r2_bucket_name, Key=key, Body=data, ContentType=content_type,
    )
    if metadata:
        kwargs["Metadata"] = {k: str(v) for k, v in metadata.items()}
    client = get_client()
    client.put_object(**kwargs)


def head_object_sync(key: str) -> bool:
    """对象存在返回 True，404/NoSuchKey 返回 False，其他异常上抛。"""
    from botocore.exceptions import ClientError

    client = get_client()
    try:
        client.head_object(Bucket=config.r2_bucket_name, Key=key)
        return True
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in ("404", "NoSuchKey", "NotFound") or status == 404:
            return False
        raise


def head_object_meta_sync(key: str) -> dict | None:
    """HEAD 对象并返回用户自定义元数据，不存在返回 None。"""
    from botocore.exceptions import ClientError

    client = get_client()
    try:
        resp = client.head_object(Bucket=config.r2_bucket_name, Key=key)
        return resp.get("Metadata") or {}
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in ("404", "NoSuchKey", "NotFound") or status == 404:
            return None
        raise


def delete_object_sync(key: str):
    client = get_client()
    client.delete_object(Bucket=config.r2_bucket_name, Key=key)


def public_url_for(key: str) -> str:
    base = (config.r2_public_url or "").rstrip("/")
    return f"{base}/{key}"
