"""Tests for the MCP server tools."""

import yaml
import pytest

from unittest.mock import MagicMock

from iacs.mcp_server import (
    _DATABASE_URL_ENV_VAR,
    _EXAMPLE_MANIFEST,
    _BUILTINS_DIR,
    _IACS_MANIFEST_DIR,
    _MANIFEST_ENV_VAR,
    _registrars,
    _available_audit_components,
    _build_format_description,
    _parse_database_url_env,
    _parse_manifest_env,
    _validate_yaml_string,
    generate_report,
    get_manifest_path,
    list_component_types,
    load_database,
    load_manifest,
    merge_yaml,
    refresh,
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


class TestParseDatabaseUrlEnv:

    def test_returns_none_when_unset(self, monkeypatch):
        monkeypatch.delenv(_DATABASE_URL_ENV_VAR, raising=False)
        assert _parse_database_url_env() is None

    def test_returns_value_when_set(self, monkeypatch, tmp_path):
        db_path = str(tmp_path / "registry.duckdb")
        monkeypatch.setenv(_DATABASE_URL_ENV_VAR, db_path)
        assert _parse_database_url_env() == db_path

    def test_returns_none_for_empty_string(self, monkeypatch):
        """An empty env var (e.g. from an unset shell interpolation) should
        fall back to manifest loading, not try to connect to "" as a URL."""
        monkeypatch.setenv(_DATABASE_URL_ENV_VAR, "")
        assert _parse_database_url_env() is None


class TestGetRegistrarPrefersDatabaseUrl:
    """`_get_registrar` should connect to an existing database-backed
    registry instead of building one from a manifest when
    IACS_DATABASE_URL is set -- this is what lets iacs-mcp share a single
    live registry with another tool (e.g. story-simulator's own per-save
    Postgres schema) instead of each holding its own separate copy."""

    def test_uses_database_registry_when_env_set(self, monkeypatch, tmp_path):
        from tests.conftest import make_registry
        from iacs.registrar import Registrar

        db_path = tmp_path / "registry.duckdb"
        Registrar(make_registry({"description": [{"entity_id": "e1", "value": "From the database."}]})).save(
            db_path
        )
        monkeypatch.setenv(_DATABASE_URL_ENV_VAR, str(db_path))

        ctx = _make_ctx()
        result = list_component_types(ctx)

        assert "description" in result
        reg = _registrars[ctx.request_context.session]
        desc = reg.registry.get("description").execute()
        assert any("From the database" in str(v) for v in desc["value"])

    def test_ignores_manifest_env_when_database_url_set(self, monkeypatch, tmp_path):
        """IACS_MANIFEST being set too shouldn't matter -- IACS_DATABASE_URL wins."""
        from tests.conftest import make_registry
        from iacs.registrar import Registrar

        db_path = tmp_path / "registry.duckdb"
        Registrar(make_registry({"description": [{"entity_id": "e1", "value": "From the database."}]})).save(
            db_path
        )
        monkeypatch.setenv(_DATABASE_URL_ENV_VAR, str(db_path))
        monkeypatch.setenv(_MANIFEST_ENV_VAR, str(_IACS_MANIFEST_DIR))

        ctx = _make_ctx()
        list_component_types(ctx)

        reg = _registrars[ctx.request_context.session]
        desc = reg.registry.get("description").execute()
        assert any("From the database" in str(v) for v in desc["value"])

    def test_falls_back_to_manifest_when_database_url_unset(self, monkeypatch):
        monkeypatch.delenv(_DATABASE_URL_ENV_VAR, raising=False)
        monkeypatch.setenv(_MANIFEST_ENV_VAR, str(_IACS_MANIFEST_DIR))

        ctx = _make_ctx()
        list_component_types(ctx)

        reg = _registrars[ctx.request_context.session]
        assert len(reg.registry.component_types) > 0


class TestLoadDatabase:
    """`load_database` is the mid-session equivalent of IACS_DATABASE_URL --
    for a URL only known once another tool has already opened its own
    registry at runtime (e.g. story-simulator's start_world telling the
    connected host what URL to pass), not knowable at server startup."""

    def _save_sample_registry(self, tmp_path):
        from tests.conftest import make_registry
        from iacs.registrar import Registrar

        db_path = tmp_path / "registry.duckdb"
        Registrar(make_registry({"description": [{"entity_id": "e1", "value": "From the database."}]})).save(
            db_path
        )
        return db_path

    def test_returns_success_string(self, tmp_path):
        db_path = self._save_sample_registry(tmp_path)
        ctx = _make_ctx()
        result = load_database(str(db_path), ctx)
        assert "Connected to database registry" in result
        assert str(db_path) in result

    def test_stores_registrar_for_session(self, tmp_path):
        db_path = self._save_sample_registry(tmp_path)
        ctx = _make_ctx()
        load_database(str(db_path), ctx)
        assert ctx.request_context.session in _registrars

    def test_loaded_registrar_reflects_database_data(self, tmp_path):
        db_path = self._save_sample_registry(tmp_path)
        ctx = _make_ctx()
        load_database(str(db_path), ctx)
        reg = _registrars[ctx.request_context.session]
        desc = reg.registry.get("description").execute()
        assert any("From the database" in str(v) for v in desc["value"])

    def test_replaces_a_previously_loaded_manifest_registry(self, tmp_path):
        """Calling load_database after load_manifest should switch this
        session over entirely, not merge the two."""
        db_path = self._save_sample_registry(tmp_path)
        ctx = _make_ctx()
        load_manifest([str(_IACS_MANIFEST_DIR)], ctx)
        load_database(str(db_path), ctx)
        reg = _registrars[ctx.request_context.session]
        desc = reg.registry.get("description").execute()
        assert list(desc["value"]) == ["From the database."]

    def test_load_database_tool_is_registered(self):
        assert "load_database" in {t.name for t in server._tool_manager.list_tools()}


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

    def test_merge_yaml_is_registered(self):
        assert "merge_yaml" in self._tool_names()


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

    def test_stores_registrar_for_session(self):
        ctx = _make_ctx()
        load_manifest([str(_IACS_MANIFEST_DIR)], ctx)
        assert ctx.request_context.session in _registrars

    def test_loaded_registrar_has_component_types(self):
        ctx = _make_ctx()
        load_manifest([str(_IACS_MANIFEST_DIR)], ctx)
        reg = _registrars[ctx.request_context.session]
        assert len(reg.registry.component_types) > 0

    def test_multiple_paths_are_merged(self, tmp_path):
        """Loading two dirs should merge entities from both into one registry."""
        (tmp_path / "extra.yaml").write_text(
            "extra_entity:\n- description: From extra dir.\n"
        )
        ctx = _make_ctx()
        load_manifest([str(_IACS_MANIFEST_DIR), str(tmp_path)], ctx)
        reg = _registrars[ctx.request_context.session]
        desc = reg.registry.get("description").execute()
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

    def test_returns_markdown_outline_by_default(self):
        """Not a table (published LLM-parsing-accuracy comparisons favor a
        key: value outline over table/CSV formats) -- a `##` heading per
        component type, `- field: value` bullets."""
        ctx = _make_ctx()
        load_manifest([str(_EXAMPLE_MANIFEST)], ctx)
        result = view_entity("make_cats_happy", ctx)
        assert "## description" in result
        assert "- value:" in result
        assert "|" not in result

    def test_markdown_excludes_internal_entity_id_columns(self):
        ctx = _make_ctx()
        load_manifest([str(_EXAMPLE_MANIFEST)], ctx)
        result = view_entity("make_cats_happy", ctx)
        assert "entity_id.hash" not in result
        assert "entity_id.path" not in result

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
        reg = _registrars[ctx.request_context.session]
        assert "requirement_coverage" in reg.registry.component_types

    def test_new_component_types_listed_in_result(self):
        ctx = _make_ctx()
        load_manifest([str(_EXAMPLE_MANIFEST)], ctx)
        result = run_dataflow("audit.requirement_coverage", ctx)
        assert "requirement_coverage" in result

    def test_run_dataflow_tool_is_registered(self):
        tool_names = {t.name for t in server._tool_manager.list_tools()}
        assert "run_dataflow" in tool_names


# ---------------------------------------------------------------------------
# refresh — MCP tool
# ---------------------------------------------------------------------------

class TestRefresh:

    def test_returns_refreshed_message(self, tmp_path):
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text(
            "my_entity:\n- description: A test entity.\n", encoding="utf-8"
        )
        ctx = _make_ctx()
        load_manifest([str(tmp_path)], ctx)
        result = refresh(ctx)
        assert "Refreshed" in result

    def test_lists_written_files(self, tmp_path):
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text(
            "my_entity:\n- description: A test entity.\n", encoding="utf-8"
        )
        ctx = _make_ctx()
        load_manifest([str(tmp_path)], ctx)
        result = refresh(ctx)
        assert "manifest.yaml" in result

    def test_files_are_actually_written(self, tmp_path):
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text(
            "my_entity:\n- description: A test entity.\n", encoding="utf-8"
        )
        ctx = _make_ctx()
        load_manifest([str(tmp_path)], ctx)
        refresh(ctx)
        assert manifest.exists()
        import yaml
        data = yaml.safe_load(manifest.read_text())
        assert "my_entity" in data

    def test_refresh_tool_is_registered(self):
        tool_names = {t.name for t in server._tool_manager.list_tools()}
        assert "refresh" in tool_names


# ---------------------------------------------------------------------------
# generate_report — MCP tool
# ---------------------------------------------------------------------------

class TestGenerateReport:

    def test_returns_written_message(self, tmp_path):
        ctx = _make_ctx()
        load_manifest(["examples/impact-cost_analysis"], ctx)
        out_path = tmp_path / "report.html"
        result = generate_report(ctx, str(out_path))
        assert "Report written to" in result
        assert str(out_path) in result

    def test_file_is_actually_written(self, tmp_path):
        ctx = _make_ctx()
        load_manifest(["examples/impact-cost_analysis"], ctx)
        out_path = tmp_path / "report.html"
        generate_report(ctx, str(out_path))
        assert out_path.exists()
        assert "<title>iacs Audit Report</title>" in out_path.read_text(encoding="utf-8")

    def test_generate_report_tool_is_registered(self):
        tool_names = {t.name for t in server._tool_manager.list_tools()}
        assert "generate_report" in tool_names


# ---------------------------------------------------------------------------
# merge_yaml — MCP tool
# ---------------------------------------------------------------------------

class TestMergeYaml:

    def test_valid_write_merges_and_reports_success(self):
        ctx = _make_ctx()
        load_manifest([str(_EXAMPLE_MANIFEST)], ctx)
        result = merge_yaml(
            "feed_cats:\n    - description:\n        value: A freshly-recorded note.\n",
            ctx,
        )
        assert "Merged" in result

    def test_valid_write_is_actually_persisted(self):
        ctx = _make_ctx()
        load_manifest([str(_EXAMPLE_MANIFEST)], ctx)
        merge_yaml(
            "feed_cats:\n    - description:\n        value: A freshly-recorded note.\n",
            ctx,
        )
        reg = _registrars[ctx.request_context.session]
        desc = reg.registry.get("description").execute()
        assert any("A freshly-recorded note" in str(v) for v in desc["value"])

    def test_bare_mapping_component_raises(self):
        ctx = _make_ctx()
        load_manifest([str(_EXAMPLE_MANIFEST)], ctx)
        with pytest.raises(ValueError, match="bare mapping"):
            merge_yaml("feed_cats:\n    description:\n        value: x\n", ctx)

    def test_unknown_component_type_raises(self):
        ctx = _make_ctx()
        load_manifest([str(_EXAMPLE_MANIFEST)], ctx)
        with pytest.raises(ValueError, match="Unknown component type"):
            merge_yaml("feed_cats:\n    - definitely_not_a_real_component:\n        value: x\n", ctx)

    def test_component_named_as_nested_entity_raises(self):
        ctx = _make_ctx()
        load_manifest([str(_EXAMPLE_MANIFEST)], ctx)
        with pytest.raises(ValueError, match="nested"):
            merge_yaml("feed_cats:\n    description:\n        - value: x\n", ctx)

    def test_inline_component_type_definition_is_accepted(self):
        """A write that declares a brand-new component type inline (its own
        component_type marker) must not be rejected as unknown -- same
        shape a manifest's own builtin component definitions use."""
        ctx = _make_ctx()
        load_manifest([str(_EXAMPLE_MANIFEST)], ctx)
        result = merge_yaml(
            "brand_new_component:\n"
            "    - description: A freshly-declared component type.\n"
            "    - component_type\n"
            "    - field:\n"
            "        value:\n"
            "            description: Its one field.\n"
            "            type: str\n"
            "\n"
            "feed_cats:\n"
            "    - brand_new_component:\n"
            "        value: hello\n",
            ctx,
        )
        assert "Merged" in result

    def test_merge_yaml_tool_is_registered(self):
        tool_names = {t.name for t in server._tool_manager.list_tools()}
        assert "merge_yaml" in tool_names
