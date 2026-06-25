"""
Router Agent

职责：扫描所有 skill 目录，从每个 skill.md 的 YAML frontmatter 中提取
name 和 description，构建轻量路由上下文，交给 LLM 判断路由到哪个 skill。

设计参考 Cursor 的 skill 路由机制：
- 路由阶段：只把 name + description 注入上下文（轻量）
- 执行阶段：再由 executor 懒加载完整 skill.md 正文
"""

import yaml
from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from config.settings import settings

SKILLS_DIR = Path(__file__).parent.parent / "skills"

ROUTER_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """你是一个技能路由器。根据用户的消息，从以下可用技能中选择最匹配的一个。

可用技能：
{skill_registry}

规则：
- 只返回技能的 name 字段值，不要解释，不要加引号
- 如果没有任何匹配的技能，返回 none
- 只返回一个技能名称""",
    ),
    ("human", "{user_message}"),
])


def _build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        temperature=0,
    )


def load_skill_registry() -> str:
    """
    扫描 skills/ 目录，读取每个 skill.md 的 YAML frontmatter，
    返回供路由使用的轻量描述文本。
    """
    entries = []
    for skill_md in sorted(SKILLS_DIR.glob("*/skill.md")):
        skill_name = skill_md.parent.name
        raw = skill_md.read_text(encoding="utf-8")

        # 解析 YAML frontmatter（--- ... --- 之间的内容）
        frontmatter = _parse_frontmatter(raw)
        name = frontmatter.get("name", skill_name)
        description = frontmatter.get("description", "")

        entries.append(f"name: {name}\ndescription: {description}")

    return "\n\n".join(entries)


def _parse_frontmatter(raw: str) -> dict:
    """提取 YAML frontmatter，格式为文件开头的 --- ... --- 块。"""
    if not raw.startswith("---"):
        return {}
    end = raw.find("---", 3)
    if end == -1:
        return {}
    try:
        return yaml.safe_load(raw[3:end]) or {}
    except yaml.YAMLError:
        return {}


def route(user_message: str) -> str:
    """
    根据用户消息路由到对应 skill。

    Returns:
        skill 目录名（如 resume_screening），或 'none'
    """
    skill_registry = load_skill_registry()
    llm = _build_llm()
    chain = ROUTER_PROMPT | llm

    result = chain.invoke({
        "skill_registry": skill_registry,
        "user_message": user_message,
    })

    skill_name = result.content.strip().lower().replace("-", "_")

    # 验证返回的 skill 名是否真实存在
    valid_skills = {p.parent.name for p in SKILLS_DIR.glob("*/skill.md")}
    if skill_name not in valid_skills:
        return "none"

    return skill_name
