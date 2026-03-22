"""Base class for iacs systems."""

import importlib
from types import ModuleType
from typing import Any

from hamilton import driver, base

from iacs.dataflows import base_etl
from iacs.registry import Registry

_DATAFLOW_BASE_PACKAGE = "iacs.dataflows"


class Architect:
    """Base class for iacs systems that operate on infrastructure data."""

    @classmethod
    def from_manifest(cls, manifest: str | list[str]) -> "Architect":
        """Create an Architect with a registry loaded and validated from a manifest.

        Args:
            manifest: A directory path (or list of paths) making up the manifest.
        """
        if isinstance(manifest, str):
            manifest = [manifest]
        result = driver.Driver(
            {}, base_etl, adapter=base.DictResult()
        ).execute(["validated_registry"], inputs={"input_dir": manifest})
        return cls(result["validated_registry"])

    def __init__(self, registry: Registry):
        self._registry = registry
        self._dataflows: list[ModuleType] = []
        self._rebuild_driver()

    def _rebuild_driver(self) -> None:
        self._driver = driver.Driver(
            {"registry": self._registry}, *self._dataflows, adapter=base.DictResult()
        )

    def load_dataflow(self, name: str) -> None:
        """Load a dataflow module by name and attach it to the driver.

        Resolves ``name`` as a dotted path within ``iacs.dataflows``, so both
        top-level modules and subpackage modules are supported::

            architect.load_dataflow("export_manifest")
            architect.load_dataflow("audit.requirement_coverage")

        Args:
            name: Dotted module path relative to ``iacs.dataflows``.

        Raises:
            ValueError: If no matching module is found.
        """
        full_name = f"{_DATAFLOW_BASE_PACKAGE}.{name}"
        try:
            module = importlib.import_module(full_name)
        except ImportError:
            raise ValueError(
                f"No dataflow named {name!r} found (tried {full_name!r})"
            )
        self._dataflows.append(module)
        self._rebuild_driver()

    @property
    def registry(self) -> Registry:
        return self._registry

    @property
    def view(self):
        return self._registry.view

    @property
    def get(self):
        return self._registry.get

    def execute(self, final_vars: str | list[str], **inputs) -> dict[str, Any]:
        """Execute DAG nodes and return their outputs.

        Args:
            final_vars: A node name, list of node names, or dataflow module
                name (e.g. ``"export_manifest"``). When a dataflow name is
                given the module is auto-loaded and all its outputs are run.
            **inputs: Additional inputs forwarded to the Hamilton driver (e.g.
                ``output_dir="..."``) to satisfy external-input nodes.
        """
        if isinstance(final_vars, str):
            full_name = f"{_DATAFLOW_BASE_PACKAGE}.{final_vars}"
            try:
                module = importlib.import_module(full_name)
                if module not in self._dataflows:
                    self._dataflows.append(module)
                    self._rebuild_driver()
                final_vars = [
                    v.name for v in self._driver.list_available_variables()
                    if not v.is_external_input
                ]
            except ImportError:
                final_vars = [final_vars]

        if not final_vars:
            return {}
        return self._driver.execute(final_vars, inputs=inputs or None)

    @property
    def outputs(self) -> list[str]:
        return [
            v.name
            for v in self._driver.list_available_variables()
            if not v.is_external_input
        ]
