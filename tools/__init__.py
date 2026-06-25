"""
工具注册中心

统一收集所有飞书工具，供 SkillExecutor 注入 Agent。
需要绑定上下文（chat_id、sender_id）的工具通过工厂函数创建。
"""

from tools.feishu_message import make_send_message_tool, make_send_message_to_user_tool
from tools.feishu_bitable import read_bitable_records, make_write_bitable_record_tool
from tools.feishu_approval import make_create_approval_tool
from tools.feishu_document import read_feishu_document


def get_all_tools(context: dict) -> list:
    """
    返回当前会话可用的全部工具列表。
    工厂函数创建的工具每次都是新实例，携带独立的状态（如去重 set），
    避免跨请求或同一请求内的重复调用。

    Args:
        context: 飞书消息上下文，包含 chat_id、sender_id 等
    """
    return [
        make_send_message_tool(context),
        make_send_message_to_user_tool(context),
        read_bitable_records,
        make_write_bitable_record_tool(),
        make_create_approval_tool(context),
        read_feishu_document,
    ]
