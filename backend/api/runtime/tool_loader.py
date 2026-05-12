import importlib
import logging

from crewai.tools import BaseTool

from api.runtime.tool_metadata import require_allowlisted_tool_module

logger = logging.getLogger(__name__)


def load_tool_class(module_path: str, class_name: str):
    require_allowlisted_tool_module(module_path)

    try:
        module = importlib.import_module(module_path)
    except Exception as exc:
        logger.exception("Failed to import tool module %s", module_path)
        raise ValueError(f"Unable to import tool module: {module_path}") from exc

    try:
        tool_class = getattr(module, class_name)
    except AttributeError as exc:
        raise ValueError(f"Tool class not found: {module_path}.{class_name}") from exc

    if not isinstance(tool_class, type) or not issubclass(tool_class, BaseTool):
        raise ValueError(f"Tool class must inherit BaseTool: {module_path}.{class_name}")

    return tool_class


def load_tool(module_path: str, class_name: str, config: dict | None = None):
    tool_class = load_tool_class(module_path, class_name)

    try:
        return tool_class(**(config or {}))
    except Exception as exc:
        raise ValueError(f"Unable to instantiate tool: {module_path}.{class_name}") from exc
