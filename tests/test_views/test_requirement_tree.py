import pytest
from pathlib import Path
from iacs.architect import Architect
from iacs.views.requirement_tree import build_requirement_tree

BASE_DIR = Path(__file__).parent.parent.parent

@pytest.fixture(scope="module")
def architect():
    return Architect.from_manifest(str(BASE_DIR / "builtins"))

def test_returns_name_and_children(architect):
    tree = build_requirement_tree(architect, "be_a_powerful_tool_for_solutions_architecture")
    assert "name" in tree
    assert "children" in tree

def test_children_sorted_by_priority(architect):
    tree = build_requirement_tree(architect, "be_a_powerful_tool_for_solutions_architecture")
    children = tree.get("children", [])
    if len(children) >= 2:
        priorities = [c.get("priority", 0.5) for c in children]
        assert priorities == sorted(priorities, reverse=True)

def test_custom_ancestor_key(architect):
    tree = build_requirement_tree(architect, "be_a_powerful_tool_for_solutions_architecture")
    assert tree["name"] == "be_a_powerful_tool_for_solutions_architecture"

def test_unknown_ancestor_key_raises(architect):
    with pytest.raises(ValueError):
        build_requirement_tree(architect, "nonexistent_key_xyz")
