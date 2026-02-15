"""Tests for parsing example manifests."""

import hashlib
from pathlib import Path

import pytest

from iacs.io_system import IOSystem


EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def eid(path: str) -> str:
    """Compute the expected entity_id for a given path (no alias)."""
    return hashlib.md5(path.encode()).hexdigest()[:12]


def entity_ids_from(data):
    """Extract unique entity_ids from a DataFrame."""
    return set(data["entity_id"].unique())


def has_component(data, entity_id, component_type):
    """Check if an entity has a given component type."""
    rows = data[
        (data["entity_id"] == entity_id)
        & (data["component_type"] == component_type)
    ]
    return len(rows) > 0


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
        eids = entity_ids_from(minimal_data)
        assert len(eids) == 2
        assert eid("my_task") in eids
        assert eid("my_infrastructure") in eids

    def test_minimal_has_expected_user_components(self, minimal_data):
        """minimal.yaml contains expected user-defined components."""
        user_rows = minimal_data[
            ~minimal_data["component_type"].isin(["id", "parent"])
        ]
        assert len(user_rows) == 4

    def test_my_task_has_description_and_task(self, minimal_data):
        """my_task entity has description and task components."""
        task_id = eid("my_task")
        assert has_component(minimal_data, task_id, "description")
        assert has_component(minimal_data, task_id, "task")

    def test_my_infrastructure_has_description_and_solution_of(self, minimal_data):
        """my_infrastructure entity has description and solution of components."""
        infra_id = eid("my_infrastructure")
        assert has_component(minimal_data, infra_id, "description")
        assert has_component(minimal_data, infra_id, "solution of")

    def test_solution_of_references_my_task(self, minimal_data):
        """The solution of component references my_task."""
        infra_id = eid("my_infrastructure")
        infra = minimal_data[minimal_data["entity_id"] == infra_id]
        solution_of = infra[infra["component_type"] == "solution of"].iloc[0]
        assert solution_of["component_value"] == {"value": eid("my_task")}


class TestMinimal2Example:
    """Tests for the minimal2 example with sub-entities.

    Note: minimal2 uses the dict format with sub-entities. Sub-entity parsing
    uses hash-based entity IDs derived from the entity path.
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
        eids = entity_ids_from(minimal2_data)
        assert eid("core_task") in eids
        assert eid("my_infrastructure") in eids

    def test_minimal2_has_sub_entities(self, minimal2_data):
        """minimal2.yaml has sub-entities with hash-based IDs."""
        eids = entity_ids_from(minimal2_data)
        assert eid("core_task.first_subtask") in eids
        assert eid("core_task.second_subtask") in eids

    def test_core_task_has_description(self, minimal2_data):
        """core_task entity has a description component from its data key."""
        assert has_component(minimal2_data, eid("core_task"), "description")

    def test_sub_entities_have_parent_component(self, minimal2_data):
        """Sub-entities have auto-generated parent components."""
        child_id = eid("core_task.first_subtask")
        parent_rows = minimal2_data[
            (minimal2_data["entity_id"] == child_id)
            & (minimal2_data["component_type"] == "parent")
        ]
        assert len(parent_rows) == 1
        cv = parent_rows.iloc[0]["component_value"]
        assert cv["target"] == eid("core_task")


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
        eids = entity_ids_from(net_ab_data)
        assert eid("A") in eids
        assert eid("B") in eids

    def test_nodes_have_node_component(self, net_ab_data):
        """Node entities have the node component."""
        assert has_component(net_ab_data, eid("A"), "node")

    def test_net_ab_has_link_entity(self, net_ab_data):
        """net_AB.yaml has link entity AB."""
        eids = entity_ids_from(net_ab_data)
        assert eid("AB") in eids

    def test_link_has_link_component(self, net_ab_data):
        """Link entity AB has a link component with source/target."""
        ab_id = eid("AB")
        ab = net_ab_data[net_ab_data["entity_id"] == ab_id]
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
        eids = entity_ids_from(net_abcd_data)
        assert eid("A") in eids
        assert eid("B") in eids
        assert eid("C") in eids
        assert eid("D") in eids

    def test_net_abcd_has_link_entities(self, net_abcd_data):
        """net_ABCD.yaml has link entities AB, BC, AD."""
        eids = entity_ids_from(net_abcd_data)
        assert eid("AB") in eids
        assert eid("BC") in eids
        assert eid("AD") in eids
