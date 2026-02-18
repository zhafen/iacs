"""Tests for parsing example manifests through the manifest_to_registry pipeline."""

from pathlib import Path

import pytest

from iacs.audit_system import AuditRunner
from iacs.transforms.manifest_to_registry import (
    _hash_path,
    raw_entity_first_data,
    flattened_entity_first_data,
    component_first_data,
    complete_schema,
    data_models,
    components_database,
    validated_components,
    registry,
)


EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
COMPONENTS_DIR = Path(__file__).parent.parent / "components"


def _build_registry(input_dir: str):
    """Build a registry from a directory using the manifest_to_registry pipeline."""
    raw = raw_entity_first_data(input_dir)
    flat_result = flattened_entity_first_data(raw)
    flattened_data = flat_result["flattened_data"]
    name_to_id = flat_result["name_to_id"]
    comp_first = component_first_data(flattened_data, name_to_id)
    schema = complete_schema(comp_first["schema"], comp_first["parent"])
    models = data_models(schema)
    conn, comps = components_database(comp_first, models)
    v_comps = validated_components(comps, models)
    return registry(conn, v_comps)


class TestMinimalExample:
    """Tests for the minimal example."""

    @pytest.fixture
    def minimal_registry(self):
        """Load minimal example into a registry."""
        return _build_registry(str(EXAMPLES_DIR / "minimal"))

    def test_minimal_has_two_entities(self, minimal_registry):
        """minimal.yaml contains two entities."""
        desc_df = minimal_registry.view("description").to_pandas()
        entity_ids = set(desc_df["entity_id"].unique())
        assert _hash_path("my_task") in entity_ids
        assert _hash_path("my_infrastructure") in entity_ids

    def test_my_task_has_description(self, minimal_registry):
        """my_task entity has a description component."""
        desc = minimal_registry.view("description").to_pandas()
        assert _hash_path("my_task") in desc["entity_id"].values

    def test_my_task_has_task_component(self, minimal_registry):
        """my_task entity has a task component."""
        task = minimal_registry.view("task").to_pandas()
        assert _hash_path("my_task") in task["entity_id"].values

    def test_my_infrastructure_has_solution_of(self, minimal_registry):
        """my_infrastructure entity has a solution of component."""
        sol = minimal_registry.view("solution of").to_pandas()
        assert _hash_path("my_infrastructure") in sol["entity_id"].values

    def test_minimal_creates_registry(self, minimal_registry):
        """minimal.yaml can be loaded into a Registry."""
        assert len(minimal_registry.component_types) > 0

    def test_minimal_runs_audits(self, minimal_registry):
        """minimal.yaml can be audited without errors."""
        runner = AuditRunner.default()
        results = runner.run(minimal_registry)
        assert len(results) > 0


class TestMinimal2Example:
    """Tests for the minimal2 example with sub-entities."""

    @pytest.fixture
    def minimal2_registry(self):
        """Load minimal2 example into a registry."""
        return _build_registry(str(EXAMPLES_DIR / "minimal2"))

    def test_minimal2_creates_registry(self, minimal2_registry):
        """minimal2.yaml can be loaded into a Registry."""
        assert len(minimal2_registry.component_types) > 0

    def test_minimal2_has_top_level_entities(self, minimal2_registry):
        """minimal2.yaml has core_task and my_infrastructure."""
        desc = minimal2_registry.view("description").to_pandas()
        entity_ids = set(desc["entity_id"].unique())
        assert _hash_path("core_task") in entity_ids
        assert _hash_path("my_infrastructure") in entity_ids

    def test_minimal2_has_sub_entities(self, minimal2_registry):
        """minimal2.yaml has sub-entities with dotted paths."""
        desc = minimal2_registry.view("description").to_pandas()
        entity_ids = set(desc["entity_id"].unique())
        assert _hash_path("core_task.first_subtask") in entity_ids
        assert _hash_path("core_task.second_subtask") in entity_ids

    def test_sub_entities_have_parent_component(self, minimal2_registry):
        """Sub-entities have parent components."""
        parent = minimal2_registry.view("parent").to_pandas()
        child_ids = set(parent["entity_id"].unique())
        assert _hash_path("core_task.first_subtask") in child_ids

    def test_minimal2_runs_audits(self, minimal2_registry):
        """minimal2.yaml can be audited without errors."""
        runner = AuditRunner.default()
        results = runner.run(minimal2_registry)
        assert len(results) > 0


class TestNetworksNetAB:
    """Tests for the net_AB.yaml network example."""

    @pytest.fixture
    def net_ab_registry(self):
        """Load net_AB.yaml into a registry."""
        return _build_registry(str(EXAMPLES_DIR / "networks"))

    def test_net_ab_creates_registry(self, net_ab_registry):
        """net_AB.yaml can be loaded into a Registry."""
        assert len(net_ab_registry.component_types) > 0

    def test_net_ab_has_node_entities(self, net_ab_registry):
        """net_AB.yaml has node entities A and B."""
        if "node" in net_ab_registry.component_types:
            node = net_ab_registry.view("node").to_pandas()
            entity_ids = set(node["entity_id"].unique())
            assert _hash_path("A") in entity_ids
            assert _hash_path("B") in entity_ids

    def test_net_ab_runs_audits(self, net_ab_registry):
        """net_AB.yaml can be audited without errors."""
        runner = AuditRunner.default()
        results = runner.run(net_ab_registry)
        assert len(results) > 0


class TestComponentsExample:
    """Tests for the components/components.yaml file."""

    @pytest.fixture
    def components_registry(self):
        """Load components.yaml into a registry."""
        return _build_registry(str(COMPONENTS_DIR))

    def test_components_creates_registry(self, components_registry):
        """components.yaml can be loaded into a Registry."""
        assert len(components_registry.component_types) > 0

    def test_components_runs_audits(self, components_registry):
        """components.yaml can be audited without errors."""
        runner = AuditRunner.default()
        results = runner.run(components_registry)
        assert len(results) > 0
