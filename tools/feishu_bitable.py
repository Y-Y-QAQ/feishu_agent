"""
飞书多维表格工具

封装飞书 bitable.v1 API，支持读取记录和写入记录。
"""

import json
import logging
from datetime import datetime, timezone

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import (
    ListAppTableRecordRequest,
    CreateAppTableRecordRequest,
    AppTableRecord,
)
from langchain_core.tools import tool
from config.settings import settings

logger = logging.getLogger(__name__)


def _build_client() -> lark.Client:
    return (
        lark.Client.builder()
        .app_id(settings.FEISHU_APP_ID)
        .app_secret(settings.FEISHU_APP_SECRET)
        .build()
    )


@tool
def read_bitable_records(filter_condition: str = "") -> str:
    """
    读取飞书多维表格中的记录。
    适用场景：查询项目进度、候选人信息、任务列表等。

    Args:
        filter_condition: 筛选条件（可选，留空则读取全部记录）
    """
    client = _build_client()
    builder = ListAppTableRecordRequest.builder() \
        .app_token(settings.BITABLE_APP_TOKEN) \
        .table_id(settings.BITABLE_TABLE_ID) \
        .page_size(50)

    if filter_condition:
        builder = builder.filter(filter_condition)

    request = builder.build()
    response = client.bitable.v1.app_table_record.list(request)

    if not response.success():
        return f"读取失败: {response.msg}"

    items = response.data.items or []
    if not items:
        return "表格中暂无记录"

    records = []
    for item in items:
        records.append(str(item.fields))

    return f"共 {len(records)} 条记录:\n" + "\n".join(records)


def make_write_bitable_record_tool():
    """
    工厂函数：返回带写入去重保护的 write_bitable_record 工具。
    去重通过写入前查表实现，不依赖闭包内存，能正确处理 LangGraph 长时间推理场景。
    """

    @tool
    def write_bitable_record(fields_json: str) -> str:
        """
        向飞书多维表格写入一条新记录。
        适用场景：记录简历评估结果、录入任务、保存分析数据等。
        注意：同一候选人在一次任务中只能写入一次，请评分确定后再调用。

        表格字段名必须严格使用：候选人姓名、目标岗位、综合评分、推荐结论、评估报告
        其中综合评分为数字，推荐结论只能是：推荐约面试 / 暂不推荐 / 待补充材料
        不要传入评估日期字段（系统自动处理）。

        Args:
            fields_json: JSON 格式的字段数据，例如：
                {"候选人姓名": "张三", "目标岗位": "AI工程师", "综合评分": 85, "推荐结论": "推荐约面试", "评估报告": "..."}
        """
        try:
            fields = json.loads(fields_json)
        except json.JSONDecodeError as e:
            logger.error("[write_bitable_record] JSON解析失败: %s | 原始内容: %s", e, fields_json)
            return f"字段格式错误，请传入合法 JSON: {e}"

        candidate_name = str(fields.get("候选人姓名", "")).strip()

        # 写入前查表去重：同名候选人今天已有记录则跳过
        if candidate_name:
            client = _build_client()
            check_req = ListAppTableRecordRequest.builder() \
                .app_token(settings.BITABLE_APP_TOKEN) \
                .table_id(settings.BITABLE_TABLE_ID) \
                .page_size(50) \
                .build()
            check_resp = client.bitable.v1.app_table_record.list(check_req)
            if check_resp.success():
                for item in (check_resp.data.items or []):
                    existing_name = str(item.fields.get("候选人姓名", "")).strip()
                    if existing_name == candidate_name:
                        logger.warning("[write_bitable_record] 候选人 %s 已存在于表格，跳过重复写入", candidate_name)
                        return f"候选人 {candidate_name} 已存在于表格，跳过重复写入"

        # 自动填入评估日期（当天 UTC 0点毫秒时间戳）
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        fields["评估日期"] = int(today.timestamp() * 1000)

        logger.info("[write_bitable_record] 准备写入字段: %s", list(fields.keys()))

        client = _build_client()
        record = AppTableRecord.builder().fields(fields).build()

        request = CreateAppTableRecordRequest.builder() \
            .app_token(settings.BITABLE_APP_TOKEN) \
            .table_id(settings.BITABLE_TABLE_ID) \
            .request_body(record) \
            .build()

        response = client.bitable.v1.app_table_record.create(request)

        if not response.success():
            logger.error("[write_bitable_record] 写入失败: code=%s msg=%s", response.code, response.msg)
            return f"写入失败(code={response.code}): {response.msg}"

        logger.info("[write_bitable_record] 写入成功: record_id=%s", response.data.record.record_id)
        return f"记录写入成功，record_id={response.data.record.record_id}"

    return write_bitable_record
