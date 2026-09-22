"""智能问答 Prompt：四段式教学回答（概念/案例/教材关联/建议）+ 无命中兜底。

所有 Prompt 集中管理；修改需记录版本。
"""

QA_PROMPT_VERSION = "0.1"

SYSTEM_PROMPT = (
    "你是一名软件建模课程的教学助手，基于教材知识库回答学生的提问。\n"
    "回答必须严格遵循以下规则：\n"
    "1. 只依据【检索到的教材上下文】回答，不得编造教材中没有的内容；\n"
    "2. 如果上下文中没有足够信息回答，明确告诉学生'教材知识库中暂无相关内容'，并给出一般性引导；\n"
    "3. 回答按四段式组织：\n"
    "   【概念解释】用一两句话给出准确定义；\n"
    "   【通俗案例】用一个贴近生活的比喻或教材中的案例帮助理解；\n"
    "   【教材关联】指出该内容在教材中的位置（如：任务二·用例图 2.1 节）；\n"
    "   【实践建议】给出 1-2 条学习或建模实践上的建议；\n"
    "4. 语言简洁、面向学生，避免堆砌术语。"
)


def build_qa_prompt(question: str, context: str) -> list[tuple[str, str]]:
    """组装 QA 对话消息。

    Args:
        question: 学生问题。
        context: RAG 检索到的教材上下文（带【来源】标注）。

    Returns:
        list[tuple[str, str]]: (role, content) 消息列表。
    """
    user_content = f"【检索到的教材上下文】\n{context}\n\n【学生提问】\n{question}\n\n请按四段式回答："
    return [("system", SYSTEM_PROMPT), ("user", user_content)]
