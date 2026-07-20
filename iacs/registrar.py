"""Base class for iacs systems."""
from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

from iacs.etl_system import ETLSystem, resolve_dataflow

if TYPE_CHECKING:
    from iacs.registry import Registry


class Registrar:
    """User-facing interface to a registry: loads human/agent-authored
    entries into it, and exposes it for viewing, updating, and exporting.
    """

    @classmethod
    def from_manifest(cls, manifest: str | Path | list[str | Path], time: Any = None) -> Registrar:
        """Create a Registrar with a registry loaded and validated from a manifest.

        Args:
            manifest: A directory path (or list of paths) making up the manifest.
            time: The point in time this manifest represents, e.g. a
                timestamp or date string. If given, any field flagged
                ``time_dimension: true`` that is still null after loading is
                filled with this value. See ``load_manifest``.
        """
        r = cls()
        r.load_manifest(manifest, time=time)
        return r

    @classmethod
    def load(cls, path: str | Path) -> Registrar:
        """Create a Registrar from a database written by ``save``.

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

    def update(
        self,
        input_dirs: str | Path | list[str | Path] | None = None,
        time: Any = None,
        **inputs,
    ) -> None:
        """Load new data and merge it into the current registry.

        The general-purpose way to grow the registry: from manifest
        directories/files, ad hoc human/agent-authored source text (e.g. an
        SCD-style position update), or both. Runs the full ETL pipeline
        (load, validate, derive); existing component types are unioned and
        deduplicated with the newly loaded data, new component types are
        added directly. The current registry is also passed into derive as
        ``existing_registry``, so a ``same_as`` component in the new data can
        target (and have its other components rebased onto) an entity from a
        prior update, not just one in this same batch.

        Args:
            input_dirs: A file path, directory path, or list of either.
            time: The point in time this data represents, e.g. a timestamp
                or date string. If given, any field flagged
                ``time_dimension: true`` in its component type's schema that
                is still null after loading is filled with this value, so
                that ``view_current`` can pick the most recent version of a
                slowly changing dimension. Only null values in the newly
                loaded components are filled; existing data is untouched.
            **inputs: Additional inputs forwarded to ``base_etl``, e.g.
                ``yaml_strings={"key": "raw yaml text"}`` or
                ``python_strings={...}``.
        """
        from iacs.dataflows import base_etl

        if isinstance(input_dirs, (str, Path)):
            input_dirs = [input_dirs]
        new_registry = self._etl.execute(
            base_etl,
            input_dirs=input_dirs or [],
            load_time=time,
            existing_registry=self._registry,
            **inputs,
        )
        self._registry.merge(new_registry)
        new_registry.close()

    def load_manifest(
        self, manifest: str | Path | list[str | Path], time: Any = None
    ) -> None:
        """Load a manifest and merge it into the current registry.

        Thin wrapper around ``update`` for the common case of loading full
        manifest directories/files from disk.

        Args:
            manifest: A file path, directory path, or list of either.
            time: The point in time this manifest represents. See ``update``.
        """
        self.update(manifest, time=time)

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

    def export_manifest(self, output_dir: str | Path | None = None) -> list[str]:
        """Export the registry back to entity-centered EC files.

        Runs the ``etl.export_manifest`` dataflow against the current
        registry, converting the relational component tables back into
        human/agent-friendly YAML entries.

        Args:
            output_dir: Directory to write the exported files to. If
                omitted, each entity is written back to its original
                source path (a "refresh" round-trip).

        Returns:
            The filepaths that were written.
        """
        kwargs = {"output_dir": str(output_dir)} if output_dir is not None else {}
        result = self.execute("etl.export_manifest", **kwargs)
        return result.get("exported_manifest_filepaths", [])

    def load_dataflow(self, name: str) -> None:
        """Load a dataflow module by name and attach it to the driver.

        Resolves ``name`` as a dotted path within ``iacs.dataflows``, so both
        top-level modules and subpackage modules are supported::

            registrar.load_dataflow("export_manifest")
            registrar.load_dataflow("audit.requirement_coverage")

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
    def view_df(self):
        return self._registry.view_df

    @property
    def view_entity(self):
        return self._registry.view_entity

    @property
    def view_entity_df(self):
        return self._registry.view_entity_df

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
