from sophia.tools.base import Tool, ToolResult


class DummyTool(Tool):
    name = "dummy"
    description = "dummy"
    parameters = {}
    authority_level = "agent"

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, data=None, message="ok")


def test_default_inject_services_is_noop():
    tool = DummyTool()
    # Should not raise
    tool.inject_services(None)  # type: ignore[arg-type]
