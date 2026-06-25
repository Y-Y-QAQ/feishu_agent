"""
飞书 Agent 主入口

使用飞书 WebSocket 长连接模式监听消息（无需公网 IP）。
收到消息后：
  1. Router 根据 skill registry 路由到对应 skill
  2. SkillExecutor 加载完整 skill 上下文，运行 ReAct Agent
  3. Agent 调用飞书工具完成任务，并回复用户
"""

import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    P2ImMessageReceiveV1,
)

from agent.router import route
from agent.executor import SkillExecutor
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Agent 启动时间戳（毫秒），忽略早于此时刻的历史消息
_startup_time_ms: int = int(time.time() * 1000)

# 已处理消息 ID 缓存，防止飞书 at-least-once 重投导致重复处理
_processed_message_ids: set[str] = set()
_processed_ids_lock = threading.Lock()

# 后台线程池，处理耗时的 Agent 任务，让 on_message 立即返回以及时 ACK
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="agent-worker")


def _extract_text(event: P2ImMessageReceiveV1) -> str:
    """从飞书消息事件中提取纯文本，去掉群聊 @mention 占位符。"""
    try:
        data = json.loads(event.event.message.content)
        text = data.get("text", "").strip()
        return re.sub(r"@_user_\d+\s*", "", text).strip()
    except Exception:
        return ""


def _extract_context(event: P2ImMessageReceiveV1) -> dict:
    """提取飞书消息上下文（chat_id、sender open_id 等）。"""
    msg = event.event.message
    sender = event.event.sender
    return {
        "chat_id": msg.chat_id or "",
        "sender_id": sender.sender_id.open_id if sender.sender_id else "",
        "message_id": msg.message_id or "",
        "chat_type": msg.chat_type or "",
    }


def _send_text(chat_id: str, text: str) -> None:
    """向指定会话发送文本消息。"""
    client = lark.Client.builder() \
        .app_id(settings.FEISHU_APP_ID) \
        .app_secret(settings.FEISHU_APP_SECRET) \
        .build()

    body = CreateMessageRequestBody.builder() \
        .receive_id(chat_id) \
        .msg_type("text") \
        .content(json.dumps({"text": text})) \
        .build()

    request = CreateMessageRequest.builder() \
        .receive_id_type("chat_id") \
        .request_body(body) \
        .build()

    client.im.v1.message.create(request)


def _process_message(text: str, context: dict) -> None:
    """在后台线程中执行路由和 Agent 推理，与 WebSocket 回调解耦。"""
    logger.info("收到消息: %s | chat_id=%s", text, context["chat_id"])

    skill_name = route(text)
    logger.info("路由结果: %s", skill_name)

    if skill_name == "none":
        _send_text(context["chat_id"],
                   "你好，我目前支持以下功能：\n"
                   "1. 简历筛选 - 发我简历文档链接，我来评估候选人\n"
                   "2. 生成周报 - 告诉我生成周报，我从表格自动整理\n"
                   "3. 数据查询 - 问我任务进度、超期情况等")
        return

    try:
        executor = SkillExecutor(skill_name)
        executor.run(text, context)
        logger.info("Skill [%s] 执行完成", skill_name)
    except Exception as e:
        logger.exception("Skill [%s] 执行异常", skill_name)
        _send_text(context["chat_id"], f"处理时遇到错误，请稍后重试。\n错误信息：{e}")


def on_message(data: P2ImMessageReceiveV1) -> None:
    """飞书消息事件回调。必须快速返回，耗时处理交给后台线程池。"""
    if not (data.event and data.event.message):
        return

    message_id = data.event.message.message_id or ""

    # 过滤 Agent 启动之前产生的历史消息，避免重连时飞书补投旧消息被误处理
    create_time_str = data.event.message.create_time or "0"
    try:
        create_time_ms = int(create_time_str)
    except ValueError:
        create_time_ms = 0
    if create_time_ms and create_time_ms < _startup_time_ms:
        logger.info("忽略历史消息 %s（create_time=%s，早于启动时间）", message_id, create_time_str)
        return

    # 加锁保证多线程下去重的原子性
    with _processed_ids_lock:
        if message_id and message_id in _processed_message_ids:
            logger.info("消息 %s 已处理过，跳过重投", message_id)
            return
        if message_id:
            _processed_message_ids.add(message_id)

    text = _extract_text(data)
    context = _extract_context(data)

    if not text:
        return

    # 提交到线程池立即返回，WebSocket 可以及时 ACK，避免飞书触发重投
    _executor.submit(_process_message, text, context)


def main():
    logger.info("飞书 Agent 启动中... APP_ID: %s",
                settings.FEISHU_APP_ID[:8] + "..." if settings.FEISHU_APP_ID else "未配置")

    event_handler = (
        lark.EventDispatcherHandler.builder(
            settings.FEISHU_ENCRYPT_KEY,
            settings.FEISHU_VERIFICATION_TOKEN,
        )
        .register_p2_im_message_receive_v1(on_message)
        .build()
    )

    ws_client = lark.ws.Client(
        settings.FEISHU_APP_ID,
        settings.FEISHU_APP_SECRET,
        event_handler=event_handler,
        auto_reconnect=True,
    )

    logger.info("飞书 Agent 已启动，等待消息...")
    ws_client.start()


if __name__ == "__main__":
    main()
