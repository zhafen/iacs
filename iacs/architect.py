"""Base class for iacs systems."""
from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iacs.registry import Registry

_DATAFLOW_BASE_PACKAGE = "iacs.dataflows"


class Architect:
    """Base class for iacs systems that operate on infrastructure data."""

    @classmethod
    def from_manifest(cls, manifest: str | Path | list[str | Path]) -> Architect:
        """Create an Architect with a registry loaded and validated from a manifest.

        Args:
            manifest: A directory path (or list of paths) making up the manifest.
        """
        a = cls()
        a.load_manifest(manifest)
        return a

    @classmethod
    def load(cls, path: str | Path) -> Architect:
        """Create an Architect from a database written by ``save``.

        This is a straight export/import of the component tables — no ETL or
        transformation is performed. The backend is inferred from ``path``
        (see ``Registry.from_database``); a plain ``.duckdb`` path uses
        DuckDB, but any ``ibis.connect``-resolvable URL works.

        Args:
            path: A URL or filesystem path resolvable by ``ibis.connect``.
        """
        from iacs.registry import Registry
        return cls(Registry.from_database(path))

    def __init__(self, registry: Registry | None = None):
        if registry is None:
            import ibis
            from iacs.registry import Registry
            registry = Registry(ibis.duckdb.connect(), {})
        self._registry = registry
        self._dataflows: list[ModuleType] = []
        self._rebuild_driver()

    def load_manifest(self, manifest: str | Path | list[str | Path]) -> None:
        """Load a manifest and merge it into the current registry.

        Runs the full ETL pipeline (load, validate, derive) on the given paths
        and unions the resulting component tables with any existing data.

        Args:
            manifest: A file path, directory path, or list of either.
        """
        from hamilton import driver, base
        from iacs.dataflows import base_etl

        if isinstance(manifest, (str, Path)):
            manifest = [manifest]
        result = driver.Driver(
            {}, base_etl, adapter=base.DictResult()
        ).execute(["registry"], inputs={"input_dirs": list(manifest)})
        new_registry = result["registry"]
        self._registry.merge(new_registry)
        new_registry.close()

    def save(self, path: str | Path) -> None:
        """Export the current registry as-is to a database.

        This is a straight export — no ETL or transformation is performed.
        The backend is inferred from ``path`` (see ``Registry.to_database``);
        a plain ``.duckdb`` path uses DuckDB, but any ``ibis.connect``-
        resolvable URL works.

        Args:
            path: A URL or filesystem path resolvable by ``ibis.connect``.
        """
        self._registry.to_database(path)

    def _rebuild_driver(self) -> None:
        from hamilton import driver, base
        self._driver = driver.Driver(
            {"registry": self._registry},
            *self._dataflows, adapter=base.DictResult(),
            allow_module_overrides=True,
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
        except ImportError as e:
            raise ValueError(
                f"No dataflow named {name!r} found (tried {full_name!r})"
            ) from e
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
