"""Tests for the load_python Hamilton DAG functions."""

from pathlib import Path

import pytest

_IACS_SRC = Path(__file__).parent.parent.parent / "iacs"

import iacs.dataflows.etl.load_manifest as load_manifest
import iacs.dataflows.etl.load_python as load_python


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
# raw_entity_first_data — parsing a dict of raw Python source
# ---------------------------------------------------------------------------

class TestRawEntityFirstData:

    def test_empty_dict_returns_empty(self):
        assert load_python.raw_entity_first_data({}) == {}

    def test_skips_entries_with_syntax_errors(self):
        result = load_python.raw_entity_first_data({"bad.py": "def (:\n"})
        assert result == {}

    def test_entries_without_docstring_or_iacs_produce_no_entities(self):
        result = load_python.raw_entity_first_data({"empty.py": "x = 1\n"})
        assert result == {}

    def test_multiple_entries_produce_separate_keys(self):
        result = load_python.raw_entity_first_data({
            "a.py": '"""Module A."""\n',
            "b.py": '"""Module B."""\n',
        })
        assert set(result.keys()) == {"a.py", "b.py"}

    def test_ignores_files_without_python_content(self):
        """A non-Python value (e.g. accidentally-included YAML text) just fails to parse."""
        result = load_python.raw_entity_first_data({"data.yaml": "key: value\n"})
        assert result == {}


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------

class TestModuleEntity:

    def test_module_docstring_becomes_description(self):
        entities = _all_entities(load_python.raw_entity_first_data({"mod.py": '"""A module docstring."""\n'}))
        key = next(k for k in entities if k.endswith("mod"))
        comps = entities[key]
        assert any(c.get("description", "").startswith("A module docstring") for c in comps)

    def test_module_iacs_meta_becomes_component(self):
        src = '"""Doc."""\n__iacs__ = {"solution of": "some_req"}\n'
        entities = _all_entities(load_python.raw_entity_first_data({"mod.py": src}))
        key = next(k for k in entities if k.endswith("mod"))
        comps = entities[key]
        assert {"solution of": "some_req"} in comps

    def test_module_without_docstring_but_with_iacs(self):
        src = '__iacs__ = {"solution of": "req"}\n'
        entities = _all_entities(load_python.raw_entity_first_data({"mod.py": src}))
        assert any(k.endswith("mod") for k in entities)


class TestFunctionEntity:

    def test_function_docstring_becomes_description(self):
        src = 'def foo():\n    """Foo does things."""\n    pass\n'
        entities = _all_entities(load_python.raw_entity_first_data({"mod.py": src}))
        key = next(k for k in entities if k.endswith(".foo"))
        comps = entities[key]
        assert any("Foo does things" in c.get("description", "") for c in comps)

    def test_function_iacs_in_body(self):
        src = (
            'def foo():\n'
            '    """Doc."""\n'
            '    __iacs__ = {"solution of": "req"}\n'
        )
        entities = _all_entities(load_python.raw_entity_first_data({"mod.py": src}))
        key = next(k for k in entities if k.endswith(".foo"))
        assert {"solution of": "req"} in entities[key]

    def test_function_without_docstring_excluded(self):
        src = 'def foo():\n    pass\n'
        entities = _all_entities(load_python.raw_entity_first_data({"mod.py": src}))
        assert not any(k.endswith(".foo") for k in entities)


class TestClassEntity:

    def test_class_docstring_becomes_description(self):
        src = 'class MyClass:\n    """A class."""\n    pass\n'
        entities = _all_entities(load_python.raw_entity_first_data({"mod.py": src}))
        key = next(k for k in entities if k.endswith(".MyClass"))
        assert any("A class" in c.get("description", "") for c in entities[key])

    def test_class_iacs_in_body(self):
        src = 'class MyClass:\n    __iacs__ = {"solution of": "req"}\n'
        entities = _all_entities(load_python.raw_entity_first_data({"mod.py": src}))
        key = next(k for k in entities if k.endswith(".MyClass"))
        assert {"solution of": "req"} in entities[key]

    def test_method_uses_full_qualified_path(self):
        src = (
            'class MyClass:\n'
            '    def my_method(self):\n'
            '        """Method doc."""\n'
            '        __iacs__ = {"solution of": "req"}\n'
        )
        entities = _all_entities(load_python.raw_entity_first_data({"mod.py": src}))
        assert any(k.endswith(".MyClass.my_method") for k in entities)
        key = next(k for k in entities if k.endswith(".MyClass.my_method"))
        assert {"solution of": "req"} in entities[key]


# ---------------------------------------------------------------------------
# Entity ID stability
# ---------------------------------------------------------------------------

class TestEntityIdStability:

    def test_same_source_produces_same_keys(self):
        python_strings = {"mod.py": '"""Doc."""\n'}
        r1 = _all_entities(load_python.raw_entity_first_data(python_strings))
        r2 = _all_entities(load_python.raw_entity_first_data(python_strings))
        assert set(r1.keys()) == set(r2.keys())

    def test_entity_key_uses_dotted_module_path(self):
        entities = _all_entities(load_python.raw_entity_first_data({"pkg/mod.py": '"""Doc."""\n'}))
        assert any("pkg.mod" in k for k in entities)


# ---------------------------------------------------------------------------
# Integration with pathvalue_pairs
# ---------------------------------------------------------------------------

class TestIntegrationWithPipeline:

    def test_entity_first_dict_feeds_pathvalue_pairs(self):
        """Python entities flow through pathvalue_pairs without error."""
        src = (
            '"""Module doc."""\n'
            '__iacs__ = {"solution of": "some_req"}\n'
        )
        py_data = load_python.raw_entity_first_data({"mod.py": src})
        pvp = load_manifest.pathvalue_pairs(py_data)
        df = pvp.to_pandas()
        assert len(df) > 0
        assert "path" in df.columns
        assert "value" in df.columns

    def test_solution_component_survives_pipeline(self):
        """A __iacs__ solution component is present after keyvalue_store."""
        src = (
            '"""Module doc."""\n'
            '__iacs__ = {"solution of": "some_req"}\n'
        )
        py_data = load_python.raw_entity_first_data({"mod.py": src})
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
        python_strings = load_manifest.raw_strings([_IACS_SRC])["raw_python_strings"]
        return load_python.raw_entity_first_data(python_strings)

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

    def test_registrar_module_entity_present(self, all_entities):
        assert "iacs.registrar" in all_entities

    def test_registrar_class_entity_present(self, all_entities):
        assert "iacs.registrar.Registrar" in all_entities

    def test_registrar_method_entity_present(self, all_entities):
        assert "iacs.registrar.Registrar.from_manifest" in all_entities

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
        pvp = load_manifest.pathvalue_pairs(iacs_result)
        kvs = load_manifest.keyvalue_store(pvp)
        ct = load_manifest.component_tables(kvs)
        assert "description" in ct
        df = ct["description"].to_pandas()
        assert len(df) >= 50

    def test_registrar_from_manifest_includes_python_entities(self):
        """Registrar.from_manifest on a dir with .py files registers Python entities."""
        from iacs.registrar import Registrar
        a = Registrar.from_manifest(_IACS_SRC)
        desc = a.registry.get("description").execute()
        py_entities = desc[desc["entity_id"].isin(
            a.registry.get("entity_id").execute()
            .query("path.str.contains('.py:', regex=False)", engine="python")["value"]
        )]
        assert len(py_entities) >= 50
