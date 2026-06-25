"""
飞书审批工具

封装飞书 approval.v4 API，支持发起审批实例。
"""

import json
import lark_oapi as lark
from lark_oapi.api.approval.v4 import (
    CreateInstanceRequest,
    InstanceCreate,
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


def make_create_approval_tool(context: dict):
    """工厂函数：绑定发起人 open_id，并记录已发起的审批防止重复。"""
    operator_id = context.get("sender_id", "")
    _approved_candidates: set[str] = set()

    # 审批表单控件 ID 映射（从飞书审批定义获取的真实 widget ID）
    WIDGET_MAP = {
        "候选人姓名": ("widget17820505007470001", "input"),
        "目标岗位":   ("widget17820505157020001", "input"),
        "综合评分":   ("widget17820505382750001", "number"),
        "推荐理由":   ("widget17820505398750001", "textarea"),
    }

    @tool
    def create_approval(form_data_json: str) -> str:
        """
        发起一个飞书面试邀约审批实例。
        适用场景：简历评分 >= 80 时，请主管确认是否约面试。

        Args:
            form_data_json: JSON 格式的审批表单数据，字段名必须是以下之一：
                候选人姓名、目标岗位、综合评分、推荐理由
                例如：{"候选人姓名": "张三", "目标岗位": "AI工程师", "综合评分": 88, "推荐理由": "..."}
        """
        client = _build_client()

        try:
            form_data = json.loads(form_data_json)
        except json.JSONDecodeError as e:
            return f"表单格式错误: {e}"

        # 同一候选人只允许发起一次审批
        candidate_name = str(form_data.get("候选人姓名", "")).strip()
        if candidate_name and candidate_name in _approved_candidates:
            return f"候选人 {candidate_name} 的审批已发起过，跳过重复发起"
        if candidate_name:
            _approved_candidates.add(candidate_name)

        # 按真实 widget ID 构造表单控件列表
        form_controls = []
        for field_name, value in form_data.items():
            if field_name in WIDGET_MAP:
                widget_id, widget_type = WIDGET_MAP[field_name]
                form_controls.append({
                    "id": widget_id,
                    "type": widget_type,
                    "value": str(value),
                })

        if not form_controls:
            return "表单字段名不匹配，请使用：候选人姓名、目标岗位、综合评分、推荐理由"

        instance = InstanceCreate.builder() \
            .approval_code(settings.APPROVAL_CODE) \
            .open_id(operator_id) \
            .form(json.dumps(form_controls, ensure_ascii=False)) \
            .build()

        request = CreateInstanceRequest.builder() \
            .request_body(instance) \
            .build()

        response = client.approval.v4.instance.create(request)

        if not response.success():
            return f"审批发起失败: {response.msg}"

        return f"审批已发起，instance_code={response.data.instance_code}"

    return create_approval
