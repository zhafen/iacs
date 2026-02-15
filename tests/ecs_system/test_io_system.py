import hashlib

import pandas as pd

from iacs.io_system import IOSystem


def eid(path: str) -> str:
    """Compute the expected entity_id for a given path (no alias)."""
    return hashlib.md5(path.encode()).hexdigest()[:12]


class TestIOSystemBasics:
    """Tests for basic IOSystem functionality."""

    def test_read_empty_data_returns_empty_dataframe(self):
        """Reading empty entity-centered data produces an empty dataframe."""
        system = IOSystem()
        result = system.read_entity_centered({})

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_read_entity_centered_returns_expected_columns(self):
        """Read dataframe has the expected columns."""
        system = IOSystem()
        data = {
            "my_entity": [
                {"description": "A simple entity."},
            ]
        }

        result = system.read_entity_centered(data)

        assert "entity_id" in result.columns
        assert "component_index" in result.columns
        assert "component_type" in result.columns
        assert "component_value" in result.columns


class TestIOSystemSingleEntity:
    """Tests for reading single entities."""

    def test_read_entity_with_single_value_component(self):
        """Read an entity with a single value component."""
        system = IOSystem()
        data = {
            "my_entity": [
                {"description": "A simple entity."},
            ]
        }

        result = system.read_entity_centered(data)

        desc_rows = result[result["component_type"] == "description"]
        assert len(desc_rows) == 1
        row = desc_rows.iloc[0]
        assert row["entity_id"] == eid("my_entity")
        assert row["component_type"] == "description"
        assert row["component_value"] == {"value": "A simple entity."}

    def test_read_entity_with_tag_component(self):
        """Read an entity with a tag component (string, no value)."""
        system = IOSystem()
        data = {
            "my_task": [
                "task",
            ]
        }

        result = system.read_entity_centered(data)

        task_rows = result[result["component_type"] == "task"]
        assert len(task_rows) == 1
        row = task_rows.iloc[0]
        assert row["entity_id"] == eid("my_task")
        assert row["component_type"] == "task"
        assert row["component_value"] == {}

    def test_read_entity_with_multiple_components(self):
        """Read an entity with multiple components."""
        system = IOSystem()
        data = {
            "my_task": [
                {"description": "A task I need to complete."},
                "task",
            ]
        }

        result = system.read_entity_centered(data)

        user_rows = result[~result["component_type"].isin(["id", "parent"])]
        assert len(user_rows) == 2
        assert user_rows.iloc[0]["component_type"] == "description"
        assert user_rows.iloc[1]["component_type"] == "task"


class TestIOSystemMultipleEntities:
    """Tests for reading multiple entities."""

    def test_read_multiple_entities(self):
        """Read multiple entities from entity-centered data."""
        system = IOSystem()
        data = {
            "entity_a": [
                {"description": "First entity."},
            ],
            "entity_b": [
                {"description": "Second entity."},
            ],
        }

        result = system.read_entity_centered(data)

        entity_ids = result["entity_id"].unique().tolist()
        assert eid("entity_a") in entity_ids
        assert eid("entity_b") in entity_ids


class TestIOSystemMinimalExample:
    """Tests for reading the minimal example."""

    def test_read_minimal_example(self):
        """Read the minimal example data."""
        system = IOSystem()
        data = {
            "my_task": [
                {"description": "A task I need to complete."},
                "task",
            ],
            "my_infrastructure": [
                {"description": "Infrastructure to complete the task."},
                {"solution of": "my_task"},
            ],
        }

        result = system.read_entity_centered(data)

        # Check my_task components (excluding auto-generated)
        my_task_rows = result[
            (result["entity_id"] == eid("my_task"))
            & (~result["component_type"].isin(["id", "parent"]))
        ]
        assert len(my_task_rows) == 2

        description_row = my_task_rows[
            my_task_rows["component_type"] == "description"
        ].iloc[0]
        assert description_row["component_value"] == {
            "value": "A task I need to complete."
        }

        task_row = my_task_rows[my_task_rows["component_type"] == "task"].iloc[0]
        assert task_row["component_value"] == {}

        # Check my_infrastructure components (excluding auto-generated)
        infra_rows = result[
            (result["entity_id"] == eid("my_infrastructure"))
            & (~result["component_type"].isin(["id", "parent"]))
        ]
        assert len(infra_rows) == 2

        solution_of_row = infra_rows[
            infra_rows["component_type"] == "solution of"
        ].iloc[0]
        # Reference to my_task should be resolved to its entity_id
        assert solution_of_row["component_value"] == {"value": eid("my_task")}

    def test_read_from_file(self, tmp_path):
        """Read from an actual file path."""
        file_content = """my_task:
- description: A task I need to complete.
- task
"""
        file_path = tmp_path / "test.yaml"
        file_path.write_text(file_content)

        system = IOSystem()
        result = system.read_entity_centered_file(file_path)

        assert eid("my_task") in result["entity_id"].unique()
        desc_rows = result[result["component_type"] == "description"]
        assert len(desc_rows) == 1
        assert desc_rows.iloc[0]["entity_id"] == eid("my_task")


class TestIOSystemIdComponent:
    """Tests for auto-generated id component."""

    def test_id_component_is_auto_generated(self):
        """Each entity gets an auto-generated id component."""
        system = IOSystem()
        data = {
            "my_entity": [
                {"description": "A simple entity."},
            ]
        }

        result = system.read_entity_centered(data)

        id_rows = result[result["component_type"] == "id"]
        assert len(id_rows) == 1
        id_val = id_rows.iloc[0]["component_value"]
        assert id_val["key"] == "my_entity"
        assert id_val["path"] == "my_entity"
        assert id_val["alias"] is None
        assert id_val["value"] == eid("my_entity")
        assert id_val["hash"] == eid("my_entity")

    def test_hash_based_entity_id_when_no_alias(self):
        """Entity ID is hash-based when no alias is provided."""
        system = IOSystem()
        data = {
            "my_entity": [
                {"description": "No alias."},
            ]
        }

        result = system.read_entity_centered(data)

        entity_id = result["entity_id"].iloc[0]
        assert len(entity_id) == 12
        assert entity_id == eid("my_entity")

    def test_alias_based_entity_id(self):
        """Entity ID equals alias when alias is provided."""
        system = IOSystem()
        data = {
            "my_entity": [
                {"id": "custom_alias"},
                {"description": "Has an alias."},
            ]
        }

        result = system.read_entity_centered(data)

        assert "custom_alias" in result["entity_id"].unique()

    def test_id_component_has_all_fields(self):
        """Id component has value, key, path, hash, and alias fields."""
        system = IOSystem()
        data = {
            "my_entity": [
                {"id": "my_alias"},
                {"description": "Test."},
            ]
        }

        result = system.read_entity_centered(data)
        id_row = result[result["component_type"] == "id"].iloc[0]
        cv = id_row["component_value"]

        assert cv["value"] == "my_alias"
        assert cv["key"] == "my_entity"
        assert cv["path"] == "my_entity"
        assert cv["alias"] == "my_alias"
        assert len(cv["hash"]) == 12


class TestIOSystemParentComponent:
    """Tests for auto-generated parent component."""

    def test_parent_component_for_sub_entities(self):
        """Sub-entities get an auto-generated parent component."""
        system = IOSystem()
        data = {
            "parent_ent": {
                "data": [
                    {"description": "Parent entity."},
                ],
                "child_ent": [
                    {"description": "Child entity."},
                ],
            },
        }

        result = system.read_entity_centered(data)

        child_id = eid("parent_ent.child_ent")
        parent_id = eid("parent_ent")
        parent_rows = result[
            (result["entity_id"] == child_id)
            & (result["component_type"] == "parent")
        ]
        assert len(parent_rows) == 1
        cv = parent_rows.iloc[0]["component_value"]
        assert cv["source"] == child_id
        assert cv["target"] == parent_id

    def test_no_parent_component_for_top_level_entities(self):
        """Top-level entities do not get a parent component."""
        system = IOSystem()
        data = {
            "top_level": [
                {"description": "Top level entity."},
            ]
        }

        result = system.read_entity_centered(data)

        parent_rows = result[result["component_type"] == "parent"]
        assert len(parent_rows) == 0


class TestIOSystemReferenceResolution:
    """Tests for reference resolution."""

    def test_exact_path_reference_resolved(self):
        """References matching exact paths are resolved to entity_ids."""
        system = IOSystem()
        data = {
            "my_task": [
                {"description": "A task."},
                "requirement",
            ],
            "my_solution": [
                {"solution of": "my_task"},
            ],
        }

        result = system.read_entity_centered(data)

        sol_row = result[result["component_type"] == "solution of"].iloc[0]
        assert sol_row["component_value"]["value"] == eid("my_task")

    def test_suffix_reference_resolved(self):
        """References matching an unambiguous suffix are resolved."""
        system = IOSystem()
        data = {
            "parent_ent": {
                "data": [
                    {"description": "Parent."},
                ],
                "child_req": [
                    {"description": "Child."},
                    "requirement",
                ],
            },
            "solution": [
                {"solution of": "child_req"},
            ],
        }

        result = system.read_entity_centered(data)

        sol_row = result[result["component_type"] == "solution of"].iloc[0]
        # "child_req" is a suffix of "parent_ent.child_req" and is unambiguous
        assert sol_row["component_value"]["value"] == eid("parent_ent.child_req")


class TestIOSystemHierarchicalEntities:
    """Tests for hierarchical entity extraction."""

    def test_sub_entities_have_correct_entity_ids(self):
        """Sub-entities use hash-based entity_ids."""
        system = IOSystem()
        data = {
            "core_task": {
                "data": [
                    {"description": "Main task."},
                ],
                "subtask": [
                    {"description": "A subtask."},
                ],
            },
        }

        result = system.read_entity_centered(data)

        entity_ids = result["entity_id"].unique().tolist()
        assert eid("core_task") in entity_ids
        assert eid("core_task.subtask") in entity_ids

    def test_deeply_nested_entities(self):
        """Deeply nested entities are extracted correctly."""
        system = IOSystem()
        data = {
            "level1": {
                "data": [
                    {"description": "Level 1."},
                ],
                "level2": {
                    "data": [
                        {"description": "Level 2."},
                    ],
                    "level3": [
                        {"description": "Level 3."},
                    ],
                },
            },
        }

        result = system.read_entity_centered(data)

        entity_ids = result["entity_id"].unique().tolist()
        assert eid("level1") in entity_ids
        assert eid("level1.level2") in entity_ids
        assert eid("level1.level2.level3") in entity_ids
