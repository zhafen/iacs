"""Base class for iacs systems."""

from types import ModuleType
from typing import Any

from hamilton import driver, base

from iacs.dataflows import base_etl
from iacs.registry import Registry


class Architect:
    """Base class for iacs systems that operate on infrastructure data."""

    @classmethod
    def from_manifest(
        cls, manifest: str | list[str], dataflows: list[ModuleType] | None = None
    ) -> "Architect":
        """Create an Architect with a registry loaded and validated from a manifest.

        Args:
            manifest: A directory path (or list of paths) making up the manifest.
            dataflows: Optional list of Hamilton dataflow modules to attach. Defaults to [].
        """
        if isinstance(manifest, str):
            manifest = [manifest]
        result = driver.Driver(
            {}, base_etl, adapter=base.DictResult()
        ).execute(["validated_registry"], inputs={"input_dir": manifest})
        return cls(result["validated_registry"], dataflows or [])

    def __init__(self, registry: Registry, dataflows: list[ModuleType]):
        self._registry = registry
        self._driver = driver.Driver(
            {"registry": registry}, *dataflows, adapter=base.DictResult()
        )

    @property
    def registry(self) -> Registry:
        return self._registry

    def execute(self, final_vars: list[str]) -> dict[str, Any]:
        if not final_vars:
            return {}
        return self._driver.execute(final_vars)

    @property
    def outputs(self) -> list[str]:
        return [
            v.name
            for v in self._driver.list_available_variables()
            if not v.is_external_input
        ]
