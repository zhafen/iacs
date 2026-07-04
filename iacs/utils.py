import ast
import hashlib
import operator

import pandas as pd

_ARITHMETIC_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def eval_arithmetic_expr(expr: str) -> float | None:
    """Safely evaluate a simple numeric arithmetic expression string.

    Supports ``+ - * /`` and parentheses over int/float literals, e.g.
    ``"4 / 50"`` or ``"(1 + 2) * 3"``. Returns ``None`` if ``expr`` is not a
    valid expression of that form (e.g. it references names or calls).
    """
    def _eval(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _ARITHMETIC_OPS:
            return _ARITHMETIC_OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ARITHMETIC_OPS:
            return _ARITHMETIC_OPS[type(node.op)](_eval(node.operand))
        raise ValueError(f"Unsupported expression node: {node!r}")

    try:
        tree = ast.parse(expr, mode="eval").body
        return float(_eval(tree))
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError):
        return None


def dhash(path: str) -> str:
    """Return a deterministic 12-char hex hash."""
    return hashlib.sha256(path.encode()).hexdigest()[:12]

def get_id(filepath: str, path: str) -> str:
    """Get the ID from the filepath and path within the file."""

    return dhash(f"{filepath}:{path}")


def candidate_entity_ids(user_path: str, entity_id_table: pd.DataFrame) -> list[str]:
    """Return entity IDs whose full path contains user_path as a substring."""
    mask = entity_id_table["path"].str.contains(user_path, regex=False)
    return entity_id_table.loc[mask, "value"].tolist()
