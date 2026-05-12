import ast
import operator

from crewai.tools import BaseTool
from pydantic import BaseModel


class CalculatorToolInput(BaseModel):
    expression: str


class CalculatorTool(BaseTool):
    name: str = "calculator"
    description: str = "Evaluates basic arithmetic expressions."
    args_schema: type[BaseModel] = CalculatorToolInput

    _operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def _run(self, expression: str) -> str:
        parsed = ast.parse(expression, mode="eval")
        return str(self._evaluate(parsed.body))

    def _evaluate(self, node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value

        if isinstance(node, ast.BinOp) and type(node.op) in self._operators:
            left = self._evaluate(node.left)
            right = self._evaluate(node.right)
            return self._operators[type(node.op)](left, right)

        if isinstance(node, ast.UnaryOp) and type(node.op) in self._operators:
            operand = self._evaluate(node.operand)
            return self._operators[type(node.op)](operand)

        raise ValueError("Unsupported expression")
