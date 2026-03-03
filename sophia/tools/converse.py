from sophia.tools.base import Tool, ToolResult


class ConverseTool(Tool):
    """Framework-level tool that signals a conversational response is needed.

    Never actually executed — loop.py intercepts the converse candidate
    before reaching the executor. Registered so the proposer LLM sees it
    as a first-class structured tool definition alongside hat tools.
    """

    name = "converse"
    description = (
        "Respond conversationally without executing any tool. "
        "Use for greetings, general questions, chitchat, or when "
        "no available tool matches the user's intent. Choose this "
        "when no action is needed."
    )
    parameters = {}
    authority_level = "agent"

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, data=None, message="")
