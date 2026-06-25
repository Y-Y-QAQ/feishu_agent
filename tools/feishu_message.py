"""
飞书消息工具

封装飞书 im.v1 消息发送 API，供 Agent 调用。
"""

import json
import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
)
from langchain_core.tools import tool
from config.settings import settings


def _build_client() -> lark.Client:
    return (
        lark.Client.builder()
        .app_id(settings.FEISHU_APP_ID)
        .app_secret(settings.FEISHU_APP_SECRET)
        .build()
    )


def make_send_message_tool(context: dict):
    """
    工厂函数：绑定 chat_id 上下文后返回 LangChain tool。
    Agent 无需知道 chat_id，由上下文自动注入。
    每次任务执行中只允许调用一次，防止重复回复。
    """
    chat_id = context.get("chat_id", "")
    _sent = {"count": 0}

    @tool
    def send_message(content: str) -> str:
        """
        向当前飞书会话发送文本消息。
        适用场景：向用户回复分析结果、通知、摘要等。
        注意：每次任务只能调用一次，请在所有分析完成后统一调用。

        Args:
            content: 要发送的文本内容（支持 Markdown）
        """
        if _sent["count"] > 0:
            return "消息已在本次任务中发送过，请勿重复调用 send_message"
        _sent["count"] += 1

        client = _build_client()
        body = CreateMessageRequestBody.builder() \
            .receive_id(chat_id) \
            .msg_type("text") \
            .content(json.dumps({"text": content})) \
            .build()

        request = CreateMessageRequest.builder() \
            .receive_id_type("chat_id") \
            .request_body(body) \
            .build()

        response = client.im.v1.message.create(request)
        if not response.success():
            return f"发送失败: {response.msg}"
        return "消息已发送"

    return send_message


def make_send_message_to_user_tool(context: dict):
    """向指定用户发送私信（用于通知简历候选人等场景）。"""

    @tool
    def send_message_to_user(user_id: str, content: str) -> str:
        """
        向指定用户发送飞书私信。
        适用场景：通知特定用户（如面试邀请、审批结果）。

        Args:
            user_id: 飞书用户 open_id
            content: 消息内容
        """
        client = _build_client()
        body = CreateMessageRequestBody.builder() \
            .receive_id(user_id) \
            .msg_type("text") \
            .content(json.dumps({"text": content})) \
            .build()

        request = CreateMessageRequest.builder() \
            .receive_id_type("open_id") \
            .request_body(body) \
            .build()

        response = client.im.v1.message.create(request)
        if not response.success():
            return f"发送失败: {response.msg}"
        return f"已向 {user_id} 发送消息"

    return send_message_to_user
