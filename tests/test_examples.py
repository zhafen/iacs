"""Tests for parsing example manifests."""

from pathlib import Path

import pytest

from iacs.io_system import IOSystem


EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


class TestMinimalExample:
    """Tests for the minimal example."""

    @pytest.fixture
    def minimal_data(self):
        """Load minimal.yaml data."""
        system = IOSystem()
        return system.read_entity_centered_file(
            EXAMPLES_DIR / "minimal" / "minimal.yaml"
        )

    def test_minimal_has_two_entities(self, minimal_data):
        """minimal.yaml contains two entities."""
        entity_ids = minimal_data["entity_id"].unique()
        assert len(entity_ids) == 2
        assert "my_task" in entity_ids
        assert "my_infrastructure" in entity_ids

    def test_minimal_has_four_components(self, minimal_data):
        """minimal.yaml contains four components total."""
        assert len(minimal_data) == 4

    def test_my_task_has_description_and_task(self, minimal_data):
        """my_task entity has description and task components."""
        my_task = minimal_data[minimal_data["entity_id"] == "my_task"]
        component_types = my_task["component_type"].tolist()
        assert "description" in component_types
        assert "task" in component_types

    def test_my_infrastructure_has_description_and_solution_of(self, minimal_data):
        """my_infrastructure entity has description and solution of components."""
        infra = minimal_data[minimal_data["entity_id"] == "my_infrastructure"]
        component_types = infra["component_type"].tolist()
        assert "description" in component_types
        assert "solution of" in component_types

    def test_solution_of_references_my_task(self, minimal_data):
        """The solution of component references my_task."""
        infra = minimal_data[minimal_data["entity_id"] == "my_infrastructure"]
        solution_of = infra[infra["component_type"] == "solution of"].iloc[0]
        assert solution_of["component_value"] == {"value": "my_task"}


class TestMinimal2Example:
    """Tests for the minimal2 example with sub-entities.

    Note: minimal2 uses the dict format with sub-entities. Sub-entity parsing
    requires that entity IDs be constructed as "parent.child" and the "data"
    key contains components for the parent entity.
    """

    @pytest.fixture
    def minimal2_data(self):
        """Load minimal2.yaml data."""
        system = IOSystem()
        return system.read_entity_centered_file(
            EXAMPLES_DIR / "minimal2" / "minimal2.yaml"
        )

    def test_minimal2_loads_without_error(self, minimal2_data):
        """minimal2.yaml loads without error."""
        assert minimal2_data is not None

    def test_minimal2_has_top_level_entities(self, minimal2_data):
        """minimal2.yaml has core_task and my_infrastructure as top-level."""
        entity_ids = minimal2_data["entity_id"].unique()
        assert "core_task" in entity_ids
        assert "my_infrastructure" in entity_ids

    def test_minimal2_has_sub_entities(self, minimal2_data):
        """minimal2.yaml has sub-entities with dotted IDs."""
        entity_ids = minimal2_data["entity_id"].unique()
        assert "core_task.first_subtask" in entity_ids
        assert "core_task.second_subtask" in entity_ids

    def test_core_task_has_description(self, minimal2_data):
        """core_task entity has a description component from its data key."""
        core_task = minimal2_data[minimal2_data["entity_id"] == "core_task"]
        component_types = core_task["component_type"].tolist()
        assert "description" in component_types


class TestNetworksNetAB:
    """Tests for the net_AB.yaml network example."""

    @pytest.fixture
    def net_ab_data(self):
        """Load net_AB.yaml data."""
        system = IOSystem()
        return system.read_entity_centered_file(
            EXAMPLES_DIR / "networks" / "net_AB.yaml"
        )

    def test_net_ab_loads_without_error(self, net_ab_data):
        """net_AB.yaml loads without error."""
        assert net_ab_data is not None
        assert len(net_ab_data) > 0

    def test_net_ab_has_node_entities(self, net_ab_data):
        """net_AB.yaml has node entities A and B."""
        entity_ids = net_ab_data["entity_id"].unique()
        assert "A" in entity_ids
        assert "B" in entity_ids

    def test_nodes_have_node_component(self, net_ab_data):
        """Node entities have the node component."""
        node_a = net_ab_data[net_ab_data["entity_id"] == "A"]
        assert "node" in node_a["component_type"].tolist()

    def test_net_ab_has_link_entity(self, net_ab_data):
        """net_AB.yaml has link entity AB."""
        entity_ids = net_ab_data["entity_id"].unique()
        assert "AB" in entity_ids

    def test_link_has_link_component(self, net_ab_data):
        """Link entity AB has a link component with source/target."""
        ab = net_ab_data[net_ab_data["entity_id"] == "AB"]
        link_row = ab[ab["component_type"] == "link"].iloc[0]
        assert link_row["component_value"]["value"]["source"] == "A"
        assert link_row["component_value"]["value"]["target"] == "B"


class TestNetworksNetABCD:
    """Tests for the net_ABCD.yaml network example."""

    @pytest.fixture
    def net_abcd_data(self):
        """Load net_ABCD.yaml data."""
        system = IOSystem()
        return system.read_entity_centered_file(
            EXAMPLES_DIR / "networks" / "net_ABCD.yaml"
        )

    def test_net_abcd_loads_without_error(self, net_abcd_data):
        """net_ABCD.yaml loads without error."""
        assert net_abcd_data is not None
        assert len(net_abcd_data) > 0

    def test_net_abcd_has_four_node_entities(self, net_abcd_data):
        """net_ABCD.yaml has node entities A, B, C, D."""
        entity_ids = net_abcd_data["entity_id"].unique()
        assert "A" in entity_ids
        assert "B" in entity_ids
        assert "C" in entity_ids
        assert "D" in entity_ids

    def test_net_abcd_has_link_entities(self, net_abcd_data):
        """net_ABCD.yaml has link entities AB, BC, AD."""
        entity_ids = net_abcd_data["entity_id"].unique()
        assert "AB" in entity_ids
        assert "BC" in entity_ids
        assert "AD" in entity_ids
