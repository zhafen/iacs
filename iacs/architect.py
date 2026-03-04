"""Base class for iacs systems."""

from types import ModuleType
from typing import Any

from hamilton import driver, base

from iacs.registry import Registry


class Architect:
    """Base class for iacs systems that operate on infrastructure data."""

    def __init__(self, registry: Registry, dataflows: list[ModuleType]):
        self._driver = driver.Driver(
            {"registry": registry}, *dataflows, adapter=base.DictResult()
        )

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
