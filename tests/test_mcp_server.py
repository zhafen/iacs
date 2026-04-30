"""Tests for the MCP server tools."""

import pytest

from iacs.mcp_server import _FORMAT_DESCRIPTION, _validate_yaml_string, server


# ---------------------------------------------------------------------------
# describe_format — underlying data
# ---------------------------------------------------------------------------

class TestDescribeFormat:

    def test_returns_string(self):
        assert isinstance(_FORMAT_DESCRIPTION, str)

    def test_contains_example_yaml(self):
        assert "```yaml" in _FORMAT_DESCRIPTION

    def test_documents_core_component_types(self):
        for component in ("description", "requirement", "solution of", "effort", "field"):
            assert component in _FORMAT_DESCRIPTION

    def test_documents_nesting_rules(self):
        assert "data" in _FORMAT_DESCRIPTION
        assert "nested" in _FORMAT_DESCRIPTION.lower()


# ---------------------------------------------------------------------------
# validate_yaml — core logic
# ---------------------------------------------------------------------------

VALID_YAML = """\
my_requirement:
    - description: Something that must be done.
    - requirement:
          priority: 0.8

my_solution:
    - description: The implementation.
    - solution of: my_requirement
"""

INVALID_SYNTAX_YAML = """\
bad: yaml: [unclosed
  - nested: wrong
"""

EMPTY_YAML = ""


class TestValidateYamlString:

    def test_valid_yaml_returns_success(self):
        result = _validate_yaml_string(VALID_YAML)
        assert result.startswith("Valid.")

    def test_valid_yaml_lists_component_types(self):
        result = _validate_yaml_string(VALID_YAML)
        assert "description" in result
        assert "requirement" in result

    def test_invalid_syntax_returns_error(self):
        result = _validate_yaml_string(INVALID_SYNTAX_YAML)
        assert "YAML syntax error" in result

    def test_empty_yaml_returns_success(self):
        # Empty YAML is technically valid (no entities, no components)
        result = _validate_yaml_string(EMPTY_YAML)
        assert "Valid." in result

    def test_multi_level_nesting_is_valid(self):
        nested = """\
parent_req:
    data:
        - description: A parent requirement.
        - requirement:
              priority: 1
    child_req:
        - description: A child requirement.
        - requirement:
              priority: 0.5
"""
        result = _validate_yaml_string(nested)
        assert result.startswith("Valid.")

    def test_solution_of_is_valid(self):
        yaml_str = """\
req:
    - requirement:
          priority: 1

sol:
    - solution of: req
"""
        result = _validate_yaml_string(yaml_str)
        assert result.startswith("Valid.")


# ---------------------------------------------------------------------------
# MCP tool registration smoke tests
# ---------------------------------------------------------------------------

class TestMcpToolRegistration:

    def _tool_names(self):
        return {t.name for t in server._tool_manager.list_tools()}

    def test_describe_format_is_registered(self):
        assert "describe_format" in self._tool_names()

    def test_validate_yaml_is_registered(self):
        assert "validate_yaml" in self._tool_names()

    def test_validate_yaml_has_yaml_string_parameter(self):
        tools = {t.name: t for t in server._tool_manager.list_tools()}
        params = tools["validate_yaml"].parameters
        assert "yaml_string" in params.get("properties", {})

    def test_describe_format_has_no_required_parameters(self):
        tools = {t.name: t for t in server._tool_manager.list_tools()}
        params = tools["describe_format"].parameters
        assert params.get("required", []) == []
