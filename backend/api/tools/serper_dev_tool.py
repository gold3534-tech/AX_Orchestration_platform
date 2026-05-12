from crewai_tools import SerperDevTool

def build_tool(tool_config: dict):
    tool_type = tool_config["type"]
    config = tool_config.get("config", {})

    if tool_type == "serper_search":
        return SerperDevTool(
            n_results=config.get("n_results", 2)
        )

    raise ValueError(f"Unsupported tool type: {tool_type}")