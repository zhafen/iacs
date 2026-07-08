"""Generic Hamilton-based dataflow execution, decoupled from Architect."""
from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any

_DATAFLOW_BASE_PACKAGE = "iacs.dataflows"


class ETLSystem:
    """Loads dataflow modules and runs them through a Hamilton driver.

    This holds all the driver-building and execution logic that used to live
    on ``Architect``, so it can be reused wherever a Hamilton dataflow needs
    to be run without requiring a registry-backed Architect.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        dataflows: list[ModuleType] | None = None,
        adapters: list | None = None,
    ):
        self._config = dict(config or {})
        self._dataflows: list[ModuleType] = list(dataflows or [])
        self._adapters = list(adapters or [])
        self._rebuild_driver()

    def _rebuild_driver(self) -> None:
        from hamilton import driver, base
        self._driver = driver.Driver(
            self._config,
            *self._dataflows,
            adapter=[base.DictResult(), *self._adapters],
            allow_module_overrides=True,
        )

    def load_dataflow(self, name: str) -> None:
        """Load a dataflow module by name and attach it to the driver.

        Resolves ``name`` as a dotted path within ``iacs.dataflows``, so both
        top-level modules and subpackage modules are supported::

            etl_system.load_dataflow("etl.export_manifest")
            etl_system.load_dataflow("audit.requirement_coverage")

        Args:
            name: Dotted module path relative to ``iacs.dataflows``.

        Raises:
            ValueError: If no matching module is found.
        """
        full_name = f"{_DATAFLOW_BASE_PACKAGE}.{name}"
        try:
            module = importlib.import_module(full_name)
        except ImportError as e:
            raise ValueError(
                f"No dataflow named {name!r} found (tried {full_name!r})"
            ) from e
        self._dataflows.append(module)
        self._rebuild_driver()

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
