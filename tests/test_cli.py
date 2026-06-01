"""Tests for the iacs CLI."""
from __future__ import annotations

import sys
import pytest

from iacs.commands import (
    EXAMPLE_MANIFEST,
    IACS_MANIFEST_DIR,
    MANIFEST_ENV_VAR,
)
from iacs.cli import _build_parser, main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_cli(*argv: str, monkeypatch, capsys) -> tuple[str, str]:
    """Run the CLI with the given argv and return (stdout, stderr)."""
    monkeypatch.setattr(sys, "argv", ["iacs", *argv])
    main()
    captured = capsys.readouterr()
    return captured.out, captured.err


# ---------------------------------------------------------------------------
# manifest command
# ---------------------------------------------------------------------------

class TestManifestCommand:

    def test_shows_builtin_default_when_env_unset(self, monkeypatch, capsys):
        monkeypatch.delenv(MANIFEST_ENV_VAR, raising=False)
        out, _ = run_cli("manifest", monkeypatch=monkeypatch, capsys=capsys)
        assert "Manifest path" in out
        assert str(EXAMPLE_MANIFEST) in out

    def test_shows_env_var_path_when_set(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setenv(MANIFEST_ENV_VAR, str(tmp_path))
        out, _ = run_cli("manifest", monkeypatch=monkeypatch, capsys=capsys)
        assert str(tmp_path) in out
        assert MANIFEST_ENV_VAR in out

    def test_shows_explicit_manifest_flag(self, monkeypatch, capsys, tmp_path):
        monkeypatch.delenv(MANIFEST_ENV_VAR, raising=False)
        out, _ = run_cli("--manifest", str(tmp_path), "manifest", monkeypatch=monkeypatch, capsys=capsys)
        assert str(tmp_path) in out
        assert "--manifest" in out

    def test_manifest_flag_overrides_env(self, monkeypatch, capsys, tmp_path):
        env_dir = tmp_path / "env"
        flag_dir = tmp_path / "flag"
        monkeypatch.setenv(MANIFEST_ENV_VAR, str(env_dir))
        out, _ = run_cli("--manifest", str(flag_dir), "manifest", monkeypatch=monkeypatch, capsys=capsys)
        assert str(flag_dir) in out


# ---------------------------------------------------------------------------
# describe-format command
# ---------------------------------------------------------------------------

class TestDescribeFormatCommand:

    def test_outputs_format_guide(self, monkeypatch, capsys):
        out, _ = run_cli("describe-format", monkeypatch=monkeypatch, capsys=capsys)
        assert "Entity-First YAML Format" in out

    def test_output_contains_component_types(self, monkeypatch, capsys):
        out, _ = run_cli("describe-format", monkeypatch=monkeypatch, capsys=capsys)
        for component in ("description", "requirement", "solution", "effort"):
            assert component in out

    def test_output_contains_example(self, monkeypatch, capsys):
        out, _ = run_cli("describe-format", monkeypatch=monkeypatch, capsys=capsys)
        assert "```yaml" in out


# ---------------------------------------------------------------------------
# validate-yaml command
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

INVALID_SYNTAX_YAML = "bad: yaml: [unclosed\n  - nested: wrong\n"


class TestValidateYamlCommand:

    def test_valid_file_exits_zero(self, monkeypatch, capsys, tmp_path):
        f = tmp_path / "valid.yaml"
        f.write_text(VALID_YAML)
        out, _ = run_cli("validate-yaml", str(f), monkeypatch=monkeypatch, capsys=capsys)
        assert out.startswith("Valid.")

    def test_invalid_file_exits_nonzero(self, monkeypatch, capsys, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text(INVALID_SYNTAX_YAML)
        monkeypatch.setattr(sys, "argv", ["iacs", "validate-yaml", str(f)])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code != 0

    def test_valid_yaml_output_mentions_component_types(self, monkeypatch, capsys, tmp_path):
        f = tmp_path / "valid.yaml"
        f.write_text(VALID_YAML)
        out, _ = run_cli("validate-yaml", str(f), monkeypatch=monkeypatch, capsys=capsys)
        assert "description" in out
        assert "requirement" in out

    def test_reads_from_stdin(self, monkeypatch, capsys, tmp_path):
        import io
        monkeypatch.setattr(sys, "stdin", io.StringIO(VALID_YAML))
        out, _ = run_cli("validate-yaml", monkeypatch=monkeypatch, capsys=capsys)
        assert out.startswith("Valid.")


# ---------------------------------------------------------------------------
# list-types command
# ---------------------------------------------------------------------------

class TestListTypesCommand:

    def test_lists_component_types(self, monkeypatch, capsys):
        monkeypatch.delenv(MANIFEST_ENV_VAR, raising=False)
        out, _ = run_cli(
            "--manifest", str(EXAMPLE_MANIFEST),
            "list-types",
            monkeypatch=monkeypatch, capsys=capsys,
        )
        assert "description" in out

    def test_shows_available_audit_components(self, monkeypatch, capsys):
        out, _ = run_cli(
            "--manifest", str(EXAMPLE_MANIFEST),
            "list-types",
            monkeypatch=monkeypatch, capsys=capsys,
        )
        assert "requirement_coverage" in out

    def test_respects_manifest_env_var(self, monkeypatch, capsys):
        monkeypatch.setenv(MANIFEST_ENV_VAR, str(EXAMPLE_MANIFEST))
        out, _ = run_cli("list-types", monkeypatch=monkeypatch, capsys=capsys)
        assert "description" in out


# ---------------------------------------------------------------------------
# view-component command
# ---------------------------------------------------------------------------

class TestViewComponentCommand:

    def test_csv_output_by_default(self, monkeypatch, capsys):
        out, _ = run_cli(
            "--manifest", str(EXAMPLE_MANIFEST),
            "view-component", "description",
            monkeypatch=monkeypatch, capsys=capsys,
        )
        assert "entity_id" in out
        assert "," in out

    def test_markdown_output(self, monkeypatch, capsys):
        out, _ = run_cli(
            "--manifest", str(EXAMPLE_MANIFEST),
            "view-component", "description",
            "--format", "markdown",
            monkeypatch=monkeypatch, capsys=capsys,
        )
        assert "|" in out

    def test_output_contains_data(self, monkeypatch, capsys):
        out, _ = run_cli(
            "--manifest", str(EXAMPLE_MANIFEST),
            "view-component", "description",
            monkeypatch=monkeypatch, capsys=capsys,
        )
        assert len(out.strip().splitlines()) > 1


# ---------------------------------------------------------------------------
# view-entity command
# ---------------------------------------------------------------------------

class TestViewEntityCommand:

    def test_markdown_output_by_default(self, monkeypatch, capsys):
        out, _ = run_cli(
            "--manifest", str(EXAMPLE_MANIFEST),
            "view-entity", "make_cats_happy",
            monkeypatch=monkeypatch, capsys=capsys,
        )
        assert "|" in out

    def test_csv_output(self, monkeypatch, capsys):
        out, _ = run_cli(
            "--manifest", str(EXAMPLE_MANIFEST),
            "view-entity", "make_cats_happy",
            "--format", "csv",
            monkeypatch=monkeypatch, capsys=capsys,
        )
        assert "entity_id" in out

    def test_unknown_entity_returns_not_found(self, monkeypatch, capsys):
        out, _ = run_cli(
            "--manifest", str(EXAMPLE_MANIFEST),
            "view-entity", "nonexistent_xyz_entity_abc",
            monkeypatch=monkeypatch, capsys=capsys,
        )
        assert "No data found" in out


# ---------------------------------------------------------------------------
# run-dataflow command
# ---------------------------------------------------------------------------

class TestRunDataflowCommand:

    def test_runs_and_shows_new_component_data(self, monkeypatch, capsys):
        out, _ = run_cli(
            "--manifest", str(EXAMPLE_MANIFEST),
            "run-dataflow", "audit.requirement_coverage",
            monkeypatch=monkeypatch, capsys=capsys,
        )
        assert "complete" in out.lower()
        assert "requirement_coverage" in out

    def test_output_includes_component_table(self, monkeypatch, capsys):
        out, _ = run_cli(
            "--manifest", str(EXAMPLE_MANIFEST),
            "run-dataflow", "audit.requirement_coverage",
            monkeypatch=monkeypatch, capsys=capsys,
        )
        assert "|" in out  # markdown table rendered

    def test_csv_format_flag(self, monkeypatch, capsys):
        out, _ = run_cli(
            "--manifest", str(EXAMPLE_MANIFEST),
            "run-dataflow", "audit.requirement_coverage",
            "--format", "csv",
            monkeypatch=monkeypatch, capsys=capsys,
        )
        assert "entity_id" in out


# ---------------------------------------------------------------------------
# refresh command
# ---------------------------------------------------------------------------

class TestRefreshCommand:

    def test_writes_files_back_to_source(self, monkeypatch, capsys, tmp_path):
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text(
            "my_entity:\n- description: A test entity.\n", encoding="utf-8"
        )
        out, _ = run_cli(
            "--manifest", str(tmp_path),
            "refresh",
            monkeypatch=monkeypatch, capsys=capsys,
        )
        assert "Refreshed" in out
        assert manifest.exists()

    def test_output_lists_written_files(self, monkeypatch, capsys, tmp_path):
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text(
            "my_entity:\n- description: A test entity.\n", encoding="utf-8"
        )
        out, _ = run_cli(
            "--manifest", str(tmp_path),
            "refresh",
            monkeypatch=monkeypatch, capsys=capsys,
        )
        assert "manifest.yaml" in out

    def test_written_yaml_is_valid(self, monkeypatch, capsys, tmp_path):
        import yaml
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text(
            "my_entity:\n- description: A test entity.\n", encoding="utf-8"
        )
        run_cli(
            "--manifest", str(tmp_path),
            "refresh",
            monkeypatch=monkeypatch, capsys=capsys,
        )
        data = yaml.safe_load(manifest.read_text())
        assert "my_entity" in data

    def test_refresh_count_matches_source_files(self, monkeypatch, capsys, tmp_path):
        (tmp_path / "a.yaml").write_text("entity_a:\n- description: A.\n")
        (tmp_path / "b.yaml").write_text("entity_b:\n- description: B.\n")
        out, _ = run_cli(
            "--manifest", str(tmp_path),
            "refresh",
            monkeypatch=monkeypatch, capsys=capsys,
        )
        assert "2 file(s)" in out


# ---------------------------------------------------------------------------
# Argument parser structure
# ---------------------------------------------------------------------------

class TestParserStructure:

    def test_all_commands_registered(self):
        parser = _build_parser()
        choices = parser._subparsers._actions[-1].choices
        expected = {
            "manifest", "list-types", "view-component", "view-entity",
            "run-dataflow", "refresh", "describe-format", "validate-yaml",
        }
        assert expected == set(choices.keys())

    def test_manifest_flag_is_repeatable(self):
        parser = _build_parser()
        args = parser.parse_args(["--manifest", "/a", "--manifest", "/b", "manifest"])
        assert args.manifest == ["/a", "/b"]

    def test_view_component_default_format(self):
        parser = _build_parser()
        args = parser.parse_args(["view-component", "description"])
        assert args.format == "csv"

    def test_view_entity_default_format(self):
        parser = _build_parser()
        args = parser.parse_args(["view-entity", "some_entity"])
        assert args.format == "markdown"

    def test_run_dataflow_default_format(self):
        parser = _build_parser()
        args = parser.parse_args(["run-dataflow", "audit.requirement_coverage"])
        assert args.format == "markdown"
