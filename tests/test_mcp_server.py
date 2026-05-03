"""Tests for the MCP server tools."""

import asyncio

import yaml
import pytest

from iacs.mcp_server import (
    _BUILTIN_MANIFEST,
    _BUILTINS_DIR,
    _IACS_MANIFEST_DIR,
    _MANIFEST_ENV_VAR,
    _build_format_description,
    _lifespan,
    _validate_yaml_string,
    get_manifest_path,
    server,
)


# ---------------------------------------------------------------------------
# describe_format — sourced from builtins
# ---------------------------------------------------------------------------

class TestDescribeFormat:

    def test_returns_string(self):
        assert isinstance(_build_format_description(), str)

    def test_contains_example_yaml(self):
        assert "```yaml" in _build_format_description()

    def test_documents_core_component_types(self):
        result = _build_format_description()
        for component in ("description", "requirement", "solution", "effort", "field"):
            assert component in result

    def test_documents_nesting_rules(self):
        result = _build_format_description()
        assert "data" in result
        assert "nested" in result.lower() or "NESTED" in result

    def test_format_guide_yaml_is_valid(self):
        """format_guide.yaml must be parseable and have the expected root entity."""
        data = yaml.safe_load(
            (_IACS_MANIFEST_DIR / "format_guide.yaml").read_text(encoding="utf-8")
        )
        assert "entity_first_yaml_format" in data

    def test_format_guide_has_format_rules(self):
        data = yaml.safe_load(
            (_IACS_MANIFEST_DIR / "format_guide.yaml").read_text(encoding="utf-8")
        )
        fmt = data["entity_first_yaml_format"]
        assert "format_rules" in fmt

    def test_format_guide_has_canonical_example(self):
        data = yaml.safe_load(
            (_IACS_MANIFEST_DIR / "format_guide.yaml").read_text(encoding="utf-8")
        )
        fmt = data["entity_first_yaml_format"]
        assert "canonical_example" in fmt

    def test_component_specs_sourced_from_components_yaml(self):
        """Descriptions for component types should come from components.yaml."""
        comp_data = yaml.safe_load(
            (_BUILTINS_DIR / "components.yaml").read_text(encoding="utf-8")
        )
        result = _build_format_description()
        # Check that descriptions from components.yaml appear in the output
        req_entity = comp_data["iacs_component"]["impact"]["requirement"]
        req_desc = next(
            (item["description"] for item in req_entity
             if isinstance(item, dict) and "description" in item),
            None,
        )
        assert req_desc is not None
        # First sentence of the description should appear in the output
        first_sentence = req_desc.strip().split(".")[0]
        assert first_sentence in result


# ---------------------------------------------------------------------------
# validate_yaml — core logic
# ---------------------------------------------------------------------------

VALID_YAML = """\
my_requirement:
    - description: Something that must be done.
    - requirement:
          value: 0.8

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
        result = _validate_yaml_string(EMPTY_YAML)
        assert "Valid." in result

    def test_multi_level_nesting_is_valid(self):
        nested = """\
parent_req:
    data:
        - description: A parent requirement.
        - requirement:
              value: 1
    child_req:
        - description: A child requirement.
        - requirement:
              value: 0.5
"""
        result = _validate_yaml_string(nested)
        assert result.startswith("Valid.")

    def test_solution_of_is_valid(self):
        yaml_str = """\
req:
    - requirement:
          value: 1

sol:
    - solution of: req
"""
        result = _validate_yaml_string(yaml_str)
        assert result.startswith("Valid.")


# ---------------------------------------------------------------------------
# get_manifest_path
# ---------------------------------------------------------------------------

class TestGetManifestPath:

    def test_returns_builtin_path_when_env_unset(self, monkeypatch):
        monkeypatch.delenv(_MANIFEST_ENV_VAR, raising=False)
        result = get_manifest_path()
        assert str(_BUILTIN_MANIFEST) in result
        assert "built-in default" in result

    def test_returns_env_path_when_set(self, monkeypatch, tmp_path):
        monkeypatch.setenv(_MANIFEST_ENV_VAR, str(tmp_path))
        result = get_manifest_path()
        assert str(tmp_path) in result
        assert _MANIFEST_ENV_VAR in result

    def test_mentions_env_var_name(self, monkeypatch):
        monkeypatch.delenv(_MANIFEST_ENV_VAR, raising=False)
        result = get_manifest_path()
        assert _MANIFEST_ENV_VAR in result


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


# ---------------------------------------------------------------------------
# Lifespan — startup prints invalid_field to stderr
# ---------------------------------------------------------------------------

class TestLifespan:

    def _run_lifespan(self):
        async def run():
            async with _lifespan(server):
                pass
        asyncio.run(run())

    def test_lifespan_prints_invalid_field_header(self, capsys):
        self._run_lifespan()
        assert "invalid_field component:" in capsys.readouterr().err

    def test_lifespan_output_contains_column_names(self, capsys):
        self._run_lifespan()
        err = capsys.readouterr().err
        for col in ("entity_id", "component_type", "field", "error_type"):
            assert col in err
