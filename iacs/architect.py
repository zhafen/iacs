"""Base class for iacs systems."""
from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

from iacs.etl_system import ETLSystem, resolve_dataflow

if TYPE_CHECKING:
    from iacs.registry import Registry


class Architect:
    """Base class for iacs systems that operate on infrastructure data."""

    @classmethod
    def from_manifest(cls, manifest: str | Path | list[str | Path], time: Any = None) -> Architect:
        """Create an Architect with a registry loaded and validated from a manifest.

        Args:
            manifest: A directory path (or list of paths) making up the manifest.
            time: The point in time this manifest represents, e.g. a
                timestamp or date string. If given, any field flagged
                ``time_dimension: true`` that is still null after loading is
                filled with this value. See ``load_manifest``.
        """
        a = cls()
        a.load_manifest(manifest, time=time)
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
        self._etl = ETLSystem()
        self._dataflows: list[ModuleType] = []

    def load_manifest(
        self, manifest: str | Path | list[str | Path], time: Any = None
    ) -> None:
        """Load a manifest and merge it into the current registry.

        Runs the full ETL pipeline (load, validate, derive) on the given paths
        and unions the resulting component tables with any existing data.

        Args:
            manifest: A file path, directory path, or list of either.
            time: The point in time this manifest represents, e.g. a
                timestamp or date string. If given, any field flagged
                ``time_dimension: true`` in its component type's schema that
                is still null after loading is filled with this value, so
                that ``view_current`` can pick the most recent version of a
                slowly changing dimension. Only null values in the newly
                loaded components are filled; existing data is untouched.
        """
        from iacs.dataflows import base_etl

        if isinstance(manifest, (str, Path)):
            manifest = [manifest]
        new_registry = self._etl.execute(base_etl, input_dirs=manifest)
        if time is not None:
            new_registry.fill_time_dimension(time)
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
        module = resolve_dataflow(name)
        if module not in self._dataflows:
            self._dataflows.append(module)

    @property
    def registry(self) -> Registry:
        return self._registry

    @property
    def view(self):
        return self._registry.view

    @property
    def view_current(self):
        return self._registry.view_current

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
            try:
                module = resolve_dataflow(final_vars)
            except ValueError:
                final_vars = [final_vars]
            else:
                if module not in self._dataflows:
                    self._dataflows.append(module)
                final_vars = self._etl.outputs(self._dataflows)

        if not final_vars:
            return {}
        return self._etl.execute(
            self._dataflows, final_vars, registry=self._registry, **inputs
        )

    @property
    def outputs(self) -> list[str]:
        return self._etl.outputs(self._dataflows)
