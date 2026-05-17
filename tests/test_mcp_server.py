"""Tests for the MCP server tools."""

import yaml
import pytest

from unittest.mock import MagicMock

from iacs.mcp_server import (
    _EXAMPLE_MANIFEST,
    _BUILTINS_DIR,
    _IACS_MANIFEST_DIR,
    _MANIFEST_ENV_VAR,
    _architects,
    _available_audit_components,
    _build_format_description,
    _parse_manifest_env,
    _validate_yaml_string,
    get_manifest_path,
    list_component_types,
    load_manifest,
    run_dataflow,
    view_entity,
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
# get_manifest_path / parse_manifest_env
# ---------------------------------------------------------------------------

class TestParseManifestEnv:

    def test_returns_example_when_unset(self, monkeypatch):
        monkeypatch.delenv(_MANIFEST_ENV_VAR, raising=False)
        assert _parse_manifest_env() == [str(_EXAMPLE_MANIFEST)]

    def test_returns_single_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv(_MANIFEST_ENV_VAR, str(tmp_path))
        assert _parse_manifest_env() == [str(tmp_path)]

    def test_returns_multiple_paths(self, monkeypatch, tmp_path):
        import os
        p1 = str(tmp_path / "a")
        p2 = str(tmp_path / "b")
        monkeypatch.setenv(_MANIFEST_ENV_VAR, os.pathsep.join([p1, p2]))
        assert _parse_manifest_env() == [p1, p2]

    def test_strips_whitespace(self, monkeypatch, tmp_path):
        import os
        p1 = str(tmp_path / "a")
        p2 = str(tmp_path / "b")
        monkeypatch.setenv(_MANIFEST_ENV_VAR, f" {p1} {os.pathsep} {p2} ")
        assert _parse_manifest_env() == [p1, p2]


class TestGetManifestPath:

    def test_returns_builtin_path_when_env_unset(self, monkeypatch):
        monkeypatch.delenv(_MANIFEST_ENV_VAR, raising=False)
        result = get_manifest_path()
        assert str(_EXAMPLE_MANIFEST) in result
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

    def test_reports_multiple_paths(self, monkeypatch, tmp_path):
        import os
        p1 = str(tmp_path / "a")
        p2 = str(tmp_path / "b")
        monkeypatch.setenv(_MANIFEST_ENV_VAR, os.pathsep.join([p1, p2]))
        result = get_manifest_path()
        assert p1 in result
        assert p2 in result


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
# load_manifest — MCP tool
# ---------------------------------------------------------------------------

def _make_ctx():
    """Return a minimal mock Context whose session supports weak references."""
    ctx = MagicMock()
    ctx.request_context.session = MagicMock()
    return ctx


class TestLoadManifest:

    def test_returns_success_string(self):
        ctx = _make_ctx()
        result = load_manifest([str(_IACS_MANIFEST_DIR)], ctx)
        assert "Loaded manifest from" in result

    def test_return_value_contains_manifest_path(self):
        ctx = _make_ctx()
        result = load_manifest([str(_IACS_MANIFEST_DIR)], ctx)
        assert str(_IACS_MANIFEST_DIR) in result

    def test_return_value_lists_component_types(self):
        ctx = _make_ctx()
        result = load_manifest([str(_IACS_MANIFEST_DIR)], ctx)
        assert "Component types:" in result

    def test_stores_architect_for_session(self):
        ctx = _make_ctx()
        load_manifest([str(_IACS_MANIFEST_DIR)], ctx)
        assert ctx.request_context.session in _architects

    def test_loaded_architect_has_component_types(self):
        ctx = _make_ctx()
        load_manifest([str(_IACS_MANIFEST_DIR)], ctx)
        arch = _architects[ctx.request_context.session]
        assert len(arch.registry.component_types) > 0

    def test_multiple_paths_are_merged(self, tmp_path):
        """Loading two dirs should merge entities from both into one registry."""
        (tmp_path / "extra.yaml").write_text(
            "extra_entity:\n- description: From extra dir.\n"
        )
        ctx = _make_ctx()
        load_manifest([str(_IACS_MANIFEST_DIR), str(tmp_path)], ctx)
        arch = _architects[ctx.request_context.session]
        desc = arch.registry.get("description").execute()
        assert any("From extra dir" in str(v) for v in desc["value"])

    def test_env_var_reported_by_get_manifest_path(self, monkeypatch):
        """When IACS_MANIFEST is set to _IACS_MANIFEST_DIR, get_manifest_path reports it."""
        monkeypatch.setenv(_MANIFEST_ENV_VAR, str(_IACS_MANIFEST_DIR))
        result = get_manifest_path()
        assert str(_IACS_MANIFEST_DIR) in result
        assert _MANIFEST_ENV_VAR in result

    def test_load_manifest_tool_is_registered(self):
        tool_names = {t.name for t in server._tool_manager.list_tools()}
        assert "load_manifest" in tool_names


# ---------------------------------------------------------------------------
# list_component_types — MCP tool
# ---------------------------------------------------------------------------

class TestListComponentTypes:

    def test_returns_string(self):
        ctx = _make_ctx()
        load_manifest([str(_EXAMPLE_MANIFEST)], ctx)
        result = list_component_types(ctx)
        assert isinstance(result, str)

    def test_includes_loaded_component_types(self):
        ctx = _make_ctx()
        load_manifest([str(_EXAMPLE_MANIFEST)], ctx)
        result = list_component_types(ctx)
        assert "description" in result

    def test_lists_unloaded_audit_components(self):
        ctx = _make_ctx()
        load_manifest([str(_EXAMPLE_MANIFEST)], ctx)
        result = list_component_types(ctx)
        assert "requirement_coverage" in result
        assert "run_dataflow" in result

    def test_audit_component_absent_after_run(self):
        ctx = _make_ctx()
        load_manifest([str(_EXAMPLE_MANIFEST)], ctx)
        run_dataflow("audit.requirement_coverage", ctx)
        result = list_component_types(ctx)
        # requirement_coverage is now loaded, so it should not appear in the
        # "available but ungenerated" section with a run_dataflow hint
        lines = result.splitlines()
        unloaded_lines = [l for l in lines if "run_dataflow" in l]
        assert not any("requirement_coverage" in l for l in unloaded_lines)

    def test_available_audit_components_helper(self):
        audit_map = _available_audit_components()
        assert "requirement_coverage" in audit_map
        assert audit_map["requirement_coverage"] == "audit.requirement_coverage"
        assert "traceability" in audit_map
        assert "todo" in audit_map


# ---------------------------------------------------------------------------
# view_entity — MCP tool
# ---------------------------------------------------------------------------

class TestViewEntity:

    def test_returns_data_for_known_alias(self):
        ctx = _make_ctx()
        load_manifest([str(_EXAMPLE_MANIFEST)], ctx)
        result = view_entity("make_cats_happy", ctx)
        assert "description" in result

    def test_returns_markdown_by_default(self):
        ctx = _make_ctx()
        load_manifest([str(_EXAMPLE_MANIFEST)], ctx)
        result = view_entity("make_cats_happy", ctx)
        assert "|" in result

    def test_returns_csv_when_requested(self):
        ctx = _make_ctx()
        load_manifest([str(_EXAMPLE_MANIFEST)], ctx)
        result = view_entity("make_cats_happy", ctx, format="csv")
        assert "entity_id" in result

    def test_returns_not_found_for_unknown_entity(self):
        ctx = _make_ctx()
        load_manifest([str(_EXAMPLE_MANIFEST)], ctx)
        result = view_entity("nonexistent_xyz_entity", ctx)
        assert "No data found" in result

    def test_view_entity_tool_is_registered(self):
        tool_names = {t.name for t in server._tool_manager.list_tools()}
        assert "view_entity" in tool_names


# ---------------------------------------------------------------------------
# run_dataflow — MCP tool
# ---------------------------------------------------------------------------

class TestRunDataflow:

    def test_returns_completion_message(self):
        ctx = _make_ctx()
        load_manifest([str(_EXAMPLE_MANIFEST)], ctx)
        result = run_dataflow("audit.requirement_coverage", ctx)
        assert "complete" in result.lower()

    def test_adds_requirement_coverage_component(self):
        ctx = _make_ctx()
        load_manifest([str(_EXAMPLE_MANIFEST)], ctx)
        run_dataflow("audit.requirement_coverage", ctx)
        arch = _architects[ctx.request_context.session]
        assert "requirement_coverage" in arch.registry.component_types

    def test_new_component_types_listed_in_result(self):
        ctx = _make_ctx()
        load_manifest([str(_EXAMPLE_MANIFEST)], ctx)
        result = run_dataflow("audit.requirement_coverage", ctx)
        assert "requirement_coverage" in result

    def test_run_dataflow_tool_is_registered(self):
        tool_names = {t.name for t in server._tool_manager.list_tools()}
        assert "run_dataflow" in tool_names
