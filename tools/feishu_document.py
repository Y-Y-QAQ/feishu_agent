"""
飞书文档工具

封装飞书 docx.v1 API，支持读取文档内容。
"""

import lark_oapi as lark
from lark_oapi.api.docx.v1 import RawContentDocumentRequest
from langchain_core.tools import tool
from config.settings import settings


def _build_client() -> lark.Client:
    return (
        lark.Client.builder()
        .app_id(settings.FEISHU_APP_ID)
        .app_secret(settings.FEISHU_APP_SECRET)
        .build()
    )


@tool
def read_feishu_document(document_id: str) -> str:
    """
    读取飞书文档的纯文本内容。
    适用场景：读取简历文档、会议纪要、项目说明等。

    Args:
        document_id: 飞书文档 ID（从文档 URL 中获取，如
            https://xxx.feishu.cn/docx/AbCdEfGh 中的 AbCdEfGh）
    """
    client = _build_client()

    request = RawContentDocumentRequest.builder() \
        .document_id(document_id) \
        .lang(0) \
        .build()

    response = client.docx.v1.document.raw_content(request)

    if not response.success():
        return f"读取文档失败: {response.msg}"

    content = response.data.content if response.data else ""
    if not content:
        return "文档内容为空"

    max_chars = 8000
    if len(content) > max_chars:
        return content[:max_chars] + f"\n\n[文档过长，已截断，共 {len(content)} 字符]"

    return content
