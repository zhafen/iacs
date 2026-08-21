"""This module contains tests that have carefully been vetted by a human contributor.

The load-example-manifest / apply-transformation / compare-to-expected.py
framework these tests are built on is generic and lives in emc2p now
(`emc2p.testing.expected_fixtures`) -- iacs just supplies its own
`examples/`/`expected/` layout and the module prefixes its own dataflow
package (plus emc2p's own, which iacs's base ETL subdags in) can show up
under. See that module's own docstring for the full framework contract.
"""

from pathlib import Path

from emc2p.testing.expected_fixtures import (
    ExpectedValueChecker,
    assert_registries_equal,
    example_dirs,
)
import pytest

from iacs.registrar import Registrar

ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = ROOT / "examples"
EXPECTED_DIR = ROOT / "tests" / "test_dataflows" / "expected"
# Dataflow nodes now come from two packages: iacs's own domain-specific
# dataflows, and emc2p's generic ones that iacs's base_etl subdags in. Both
# map onto the same expected/<example>/<subpath>.py fixture layout.
DATAFLOW_MODULE_PREFIXES = ("iacs.dataflows.", "emc2p.dataflows.")


@pytest.mark.parametrize("example_dir", example_dirs(EXAMPLES_DIR))
def test_end_to_end(example_dir: Path, tmp_path: Path):
    """Thorough end to end test that:
    1. Runs base_etl for each example manifest
    2. Runs export_manifest on the loaded registry
    3. Runs base_etl on the exported manifest

    In terms of comparisons, for each executed DAG node the outputs are compared to
    manually input expectations. At the end all components in the originally loaded
    registry are compared to the components of the reloaded registry.
    """

    checker = ExpectedValueChecker(example_dir, EXPECTED_DIR, DATAFLOW_MODULE_PREFIXES)
    registrar = Registrar()

    # Get the loaded registry, comparing outputs along the way
    registrar.update(input_dirs=[str(example_dir)], adapters=[checker])

    # Export back to manifest format, comparing outputs along the way
    output_dir = tmp_path / example_dir.name
    registrar.execute(
        "etl.export_manifest",
        adapters=[checker],
        output_dir=str(output_dir),
    )

    # Reload. The expected fixtures encode entity IDs derived from the original
    # example_dir's filepath, so they don't apply to nodes loaded from
    # output_dir; only the final registry comparison below applies here.
    reloaded_registrar = Registrar()
    reloaded_registrar.update(input_dirs=[str(output_dir)])

    assert_registries_equal(registrar, reloaded_registrar)


def test_incremental_load_is_consistent():

    example_dir = EXAMPLES_DIR / "example"

    # Get the loaded registry
    registrar = Registrar.from_manifest(str(example_dir))

    incremental_registrar = Registrar()
    source_files = sorted(example_dir.rglob("*.yaml")) + sorted(
        example_dir.rglob("*.csv")
    )
    for source_file in source_files:
        incremental_registrar.update(input_dirs=[str(source_file)])

    assert_registries_equal(registrar, incremental_registrar)


def test_scd_support():

    # Initial registry
    example_dir = EXAMPLES_DIR / "game_data"
    registrar = Registrar.from_manifest(example_dir)

    # Get the entity_id for the player
    eids = registrar.get("entity_id")
    player_eid = (
        eids.filter(eids["alias"].contains("player")).execute().iloc[0]["value"]
    )

    # Add new player position
    input_yaml = f"""
    updated_player_position:
        - same_as:
            target_entity_id: {player_eid}
        - position:
            x: 5
            y: 5
            z: 5
    """
    registrar.update(
        input_dirs=[example_dir],
        yaml_strings={"scd_update": input_yaml},
        time=1,
    )

    # Check the current position of the player and the dimensions of the position table
    positions = registrar.view_current("position")
    assert positions.count().execute() == 1
    assert list(positions.execute().iloc[0][["position.x", "position.y", "position.z"]]) == [5, 5, 5]
