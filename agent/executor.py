"""
Skill Executor

职责：根据路由结果，懒加载对应 skill 的完整上下文（skill.md 正文 + refs + templates），
构建 LangGraph ReAct Agent，注入飞书工具，执行用户请求。
"""

from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from config.settings import settings
from tools import get_all_tools

SKILLS_DIR = Path(__file__).parent.parent / "skills"


class SkillExecutor:
    """
    加载指定 skill 的完整上下文，运行 ReAct Agent。

    懒加载策略：
    - skill.md 正文作为 system prompt 的执行指南
    - refs/ 下所有 .md 文件作为参考知识注入
    - templates/ 下所有 .md 文件作为输出模板注入
    """

    def __init__(self, skill_name: str):
        self.skill_dir = SKILLS_DIR / skill_name
        self.skill_name = skill_name

        self.skill_guide = self._load_skill_guide()
        self.refs = self._load_dir("refs")
        self.templates = self._load_dir("templates")

    def _load_skill_guide(self) -> str:
        """读取 skill.md 正文（去掉 frontmatter）。"""
        raw = (self.skill_dir / "skill.md").read_text(encoding="utf-8")
        if raw.startswith("---"):
            end = raw.find("---", 3)
            if end != -1:
                return raw[end + 3:].strip()
        return raw.strip()

    def _load_dir(self, subdir: str) -> dict[str, str]:
        """读取子目录下所有 .md 文件，返回 {文件名: 内容} 字典。"""
        target = self.skill_dir / subdir
        if not target.exists():
            return {}
        return {
            f.stem: f.read_text(encoding="utf-8")
            for f in sorted(target.glob("*.md"))
        }

    def _build_system_prompt(self) -> str:
        parts = ["# 执行指南\n", self.skill_guide]

        if self.refs:
            parts.append("\n\n# 参考资料\n")
            for name, content in self.refs.items():
                parts.append(f"\n## {name}\n{content}")

        if self.templates:
            parts.append("\n\n# 输出模板\n")
            for name, content in self.templates.items():
                parts.append(f"\n## {name}\n{content}")

        return "".join(parts)

    def run(self, user_message: str, context: dict[str, Any] | None = None) -> str:
        """
        执行 skill。

        Args:
            user_message: 用户原始消息
            context: 飞书消息上下文（sender_id、chat_id 等）

        Returns:
            Agent 最终回复内容
        """
        llm = ChatOpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL,
            temperature=0,
        )

        tools = get_all_tools(context or {})
        agent = create_agent(llm, tools)

        system_prompt = self._build_system_prompt()

        # 如果有飞书消息上下文，附加到用户消息里
        full_message = user_message
        if context:
            chat_id = context.get("chat_id", "")
            sender_id = context.get("sender_id", "")
            if chat_id or sender_id:
                full_message = (
                    f"{user_message}\n\n"
                    f"[消息上下文] chat_id={chat_id}, sender_id={sender_id}"
                )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=full_message),
        ]

        result = agent.invoke(
            {"messages": messages},
            config={"recursion_limit": 10},  # 最多 10 轮推理，防止异常循环
        )
        last_message = result["messages"][-1]
        return last_message.content
