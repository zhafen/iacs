"""Tests for the load_python Hamilton DAG functions."""

from pathlib import Path

import pytest

_IACS_SRC = str(Path(__file__).parent.parent.parent / "iacs")

import iacs.dataflows.etl.load_python as load_python
from iacs.utils import dhash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path, filename, content):
    f = tmp_path / filename
    f.write_text(content)
    return str(tmp_path)


def _all_entities(result: dict) -> dict:
    merged = {}
    for entities in result.values():
        merged.update(entities)
    return merged


# ---------------------------------------------------------------------------
# _find_iacs_meta
# ---------------------------------------------------------------------------

class TestFindIacsMeta:

    def _parse_body(self, src):
        import ast
        return ast.parse(src).body

    def test_finds_module_level_assignment(self):
        stmts = self._parse_body('__iacs__ = {"solution of": "req"}')
        result = load_python._find_iacs_meta(stmts)
        assert result == {"solution of": "req"}

    def test_finds_after_docstring(self):
        stmts = self._parse_body('"""Docstring."""\n__iacs__ = {"solution of": "req"}')
        result = load_python._find_iacs_meta(stmts)
        assert result == {"solution of": "req"}

    def test_returns_none_when_absent(self):
        stmts = self._parse_body("x = 1\ny = 2")
        assert load_python._find_iacs_meta(stmts) is None

    def test_ignores_non_dict_value(self):
        stmts = self._parse_body('__iacs__ = "not a dict"')
        assert load_python._find_iacs_meta(stmts) is None

    def test_multiple_keys(self):
        stmts = self._parse_body('__iacs__ = {"solution of": "r", "work_state": "done"}')
        result = load_python._find_iacs_meta(stmts)
        assert result == {"solution of": "r", "work_state": "done"}


# ---------------------------------------------------------------------------
# raw_entity_first_data — file discovery
# ---------------------------------------------------------------------------

class TestFileDiscovery:

    def test_loads_py_files_from_directory(self, tmp_path):
        _write(tmp_path, "mod.py", '"""A module."""\n')
        result = load_python.raw_entity_first_data([str(tmp_path)])
        assert isinstance(result, dict)
        assert any(k.endswith("mod.py") for k in result)

    def test_loads_explicit_py_file(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text('"""A module."""\n')
        result = load_python.raw_entity_first_data([str(f)])
        assert any(k.endswith("mod.py") for k in result)

    def test_recursive_subdirectory(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.py").write_text('"""Deep module."""\n')
        result = load_python.raw_entity_first_data([str(tmp_path)])
        assert any(k.endswith("deep.py") for k in result)

    def test_ignores_yaml_files(self, tmp_path):
        (tmp_path / "data.yaml").write_text("key: value\n")
        result = load_python.raw_entity_first_data([str(tmp_path)])
        assert result == {}

    def test_skips_files_with_syntax_errors(self, tmp_path):
        (tmp_path / "bad.py").write_text("def (:\n")
        result = load_python.raw_entity_first_data([str(tmp_path)])
        assert result == {}

    def test_empty_directory_returns_empty(self, tmp_path):
        result = load_python.raw_entity_first_data([str(tmp_path)])
        assert result == {}

    def test_file_without_docstring_or_iacs_produces_no_entities(self, tmp_path):
        _write(tmp_path, "empty.py", "x = 1\n")
        result = load_python.raw_entity_first_data([str(tmp_path)])
        assert result == {}


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------

class TestModuleEntity:

    def test_module_docstring_becomes_description(self, tmp_path):
        _write(tmp_path, "mod.py", '"""A module docstring."""\n')
        entities = _all_entities(load_python.raw_entity_first_data([str(tmp_path)]))
        key = next(k for k in entities if k.endswith("mod"))
        comps = entities[key]
        assert any(c.get("description", "").startswith("A module docstring") for c in comps)

    def test_module_iacs_meta_becomes_component(self, tmp_path):
        _write(tmp_path, "mod.py", '"""Doc."""\n__iacs__ = {"solution of": "some_req"}\n')
        entities = _all_entities(load_python.raw_entity_first_data([str(tmp_path)]))
        key = next(k for k in entities if k.endswith("mod"))
        comps = entities[key]
        assert {"solution of": "some_req"} in comps

    def test_module_without_docstring_but_with_iacs(self, tmp_path):
        _write(tmp_path, "mod.py", '__iacs__ = {"solution of": "req"}\n')
        entities = _all_entities(load_python.raw_entity_first_data([str(tmp_path)]))
        assert any(k.endswith("mod") for k in entities)


class TestFunctionEntity:

    def test_function_docstring_becomes_description(self, tmp_path):
        _write(tmp_path, "mod.py", 'def foo():\n    """Foo does things."""\n    pass\n')
        entities = _all_entities(load_python.raw_entity_first_data([str(tmp_path)]))
        key = next(k for k in entities if k.endswith(".foo"))
        comps = entities[key]
        assert any("Foo does things" in c.get("description", "") for c in comps)

    def test_function_iacs_in_body(self, tmp_path):
        src = (
            'def foo():\n'
            '    """Doc."""\n'
            '    __iacs__ = {"solution of": "req"}\n'
        )
        _write(tmp_path, "mod.py", src)
        entities = _all_entities(load_python.raw_entity_first_data([str(tmp_path)]))
        key = next(k for k in entities if k.endswith(".foo"))
        assert {"solution of": "req"} in entities[key]

    def test_function_without_docstring_excluded(self, tmp_path):
        _write(tmp_path, "mod.py", 'def foo():\n    pass\n')
        entities = _all_entities(load_python.raw_entity_first_data([str(tmp_path)]))
        assert not any(k.endswith(".foo") for k in entities)


class TestClassEntity:

    def test_class_docstring_becomes_description(self, tmp_path):
        _write(tmp_path, "mod.py", 'class MyClass:\n    """A class."""\n    pass\n')
        entities = _all_entities(load_python.raw_entity_first_data([str(tmp_path)]))
        key = next(k for k in entities if k.endswith(".MyClass"))
        assert any("A class" in c.get("description", "") for c in entities[key])

    def test_class_iacs_in_body(self, tmp_path):
        src = 'class MyClass:\n    __iacs__ = {"solution of": "req"}\n'
        _write(tmp_path, "mod.py", src)
        entities = _all_entities(load_python.raw_entity_first_data([str(tmp_path)]))
        key = next(k for k in entities if k.endswith(".MyClass"))
        assert {"solution of": "req"} in entities[key]

    def test_method_uses_full_qualified_path(self, tmp_path):
        src = (
            'class MyClass:\n'
            '    def my_method(self):\n'
            '        """Method doc."""\n'
            '        __iacs__ = {"solution of": "req"}\n'
        )
        _write(tmp_path, "mod.py", src)
        entities = _all_entities(load_python.raw_entity_first_data([str(tmp_path)]))
        assert any(k.endswith(".MyClass.my_method") for k in entities)
        key = next(k for k in entities if k.endswith(".MyClass.my_method"))
        assert {"solution of": "req"} in entities[key]


# ---------------------------------------------------------------------------
# Entity ID stability
# ---------------------------------------------------------------------------

class TestEntityIdStability:

    def test_same_file_produces_same_keys(self, tmp_path):
        _write(tmp_path, "mod.py", '"""Doc."""\n')
        r1 = _all_entities(load_python.raw_entity_first_data([str(tmp_path)]))
        r2 = _all_entities(load_python.raw_entity_first_data([str(tmp_path)]))
        assert set(r1.keys()) == set(r2.keys())

    def test_entity_key_uses_dotted_module_path(self, tmp_path):
        sub = tmp_path / "pkg"
        sub.mkdir()
        (sub / "mod.py").write_text('"""Doc."""\n')
        entities = _all_entities(load_python.raw_entity_first_data([str(tmp_path)]))
        assert any("pkg.mod" in k for k in entities)


# ---------------------------------------------------------------------------
# Integration with pathvalue_pairs
# ---------------------------------------------------------------------------

class TestIntegrationWithPipeline:

    def test_entity_first_dict_feeds_pathvalue_pairs(self, tmp_path):
        """Python entities flow through pathvalue_pairs without error."""
        import iacs.dataflows.etl.load_manifest as load_manifest
        src = (
            '"""Module doc."""\n'
            '__iacs__ = {"solution of": "some_req"}\n'
        )
        _write(tmp_path, "mod.py", src)
        py_data = load_python.raw_entity_first_data([str(tmp_path)])
        pvp = load_manifest.pathvalue_pairs(py_data)
        df = pvp.to_pandas()
        assert len(df) > 0
        assert "path" in df.columns
        assert "value" in df.columns

    def test_solution_component_survives_pipeline(self, tmp_path):
        """A __iacs__ solution component is present after keyvalue_store."""
        import iacs.dataflows.etl.load_manifest as load_manifest
        src = (
            '"""Module doc."""\n'
            '__iacs__ = {"solution of": "some_req"}\n'
        )
        _write(tmp_path, "mod.py", src)
        py_data = load_python.raw_entity_first_data([str(tmp_path)])
        pvp = load_manifest.pathvalue_pairs(py_data)
        kvs = load_manifest.keyvalue_store(pvp)
        ct = load_manifest.component_tables(kvs)
        assert "solution" in ct
        sol_df = ct["solution"].to_pandas()
        assert (sol_df["modifier"] == "of").any()
        assert (sol_df["value"] == "some_req").any()


# ---------------------------------------------------------------------------
# Integration test: load the real iacs package
# ---------------------------------------------------------------------------

class TestLoadIacsPackage:
    """Load the iacs source tree and verify the output is well-formed."""

    @pytest.fixture(scope="class")
    def iacs_result(self):
        return load_python.raw_entity_first_data([_IACS_SRC])

    @pytest.fixture(scope="class")
    def all_entities(self, iacs_result):
        merged = {}
        for entities in iacs_result.values():
            merged.update(entities)
        return merged

    def test_finds_multiple_files(self, iacs_result):
        assert len(iacs_result) >= 10

    def test_finds_many_entities(self, all_entities):
        assert len(all_entities) >= 50

    def test_keyed_by_py_file_path(self, iacs_result):
        assert all(k.endswith(".py") for k in iacs_result)

    def test_architect_module_entity_present(self, all_entities):
        assert "iacs.architect" in all_entities

    def test_architect_class_entity_present(self, all_entities):
        assert "iacs.architect.Architect" in all_entities

    def test_architect_method_entity_present(self, all_entities):
        assert "iacs.architect.Architect.from_manifest" in all_entities

    def test_load_manifest_module_entity_present(self, all_entities):
        assert "iacs.dataflows.etl.load_manifest" in all_entities

    def test_load_manifest_function_entities_present(self, all_entities):
        assert "iacs.dataflows.etl.load_manifest.raw_entity_first_data" in all_entities
        assert "iacs.dataflows.etl.load_manifest.registry" in all_entities

    def test_load_python_module_itself_present(self, all_entities):
        assert "iacs.dataflows.etl.load_python" in all_entities

    def test_description_components_are_strings(self, all_entities):
        for key, comps in all_entities.items():
            for comp in comps:
                if "description" in comp:
                    assert isinstance(comp["description"], str), key
                    assert comp["description"].strip(), key

    def test_entity_values_are_lists(self, all_entities):
        for key, val in all_entities.items():
            assert isinstance(val, list), f"{key} should be a list"

    def test_all_components_are_dicts(self, all_entities):
        for key, comps in all_entities.items():
            for comp in comps:
                assert isinstance(comp, dict), f"component in {key} should be a dict"

    def test_flows_through_pipeline_without_error(self, iacs_result):
        import iacs.dataflows.etl.load_manifest as load_manifest
        pvp = load_manifest.pathvalue_pairs(iacs_result)
        kvs = load_manifest.keyvalue_store(pvp)
        ct = load_manifest.component_tables(kvs)
        assert "description" in ct
        df = ct["description"].to_pandas()
        assert len(df) >= 50

    def test_architect_from_manifest_includes_python_entities(self):
        """Architect.from_manifest on a dir with .py files registers Python entities."""
        from iacs.architect import Architect
        a = Architect.from_manifest(_IACS_SRC)
        desc = a.registry.get("description").execute()
        py_entities = desc[desc["entity_id"].isin(
            a.registry.get("entity_id").execute()
            .query("path.str.contains('.py:', regex=False)", engine="python")["value"]
        )]
        assert len(py_entities) >= 50
