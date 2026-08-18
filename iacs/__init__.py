"""iacs: architecture-solution component definitions and dataflows built on
top of emc2p's generic Entity-Component System engine.

Registers this package's own dataflow package and builtins directory with
emc2p's extension points, so an ``iacs.registrar.Registrar`` can resolve
dotted dataflow names like ``"audit.requirement_coverage"`` and every
manifest load picks up iacs's own architecture-specific component
definitions (``requirement``, ``cost``, ``task``, ...) alongside emc2p's
generic ones (``entity_id``, ``description``, ...).
"""
from pathlib import Path

from emc2p.etl_system import register_dataflow_package
from emc2p.dataflows.etl.load_manifest import register_builtins_dir

register_dataflow_package("iacs.dataflows")
register_builtins_dir(Path(__file__).parent / "builtins", "iacs_builtins")
