"""AuditSystem for evaluating solution quality."""

from types import ModuleType

import ibis
from hamilton import driver, base

from iacs.registry import Registry


class AuditRunner:
    """Executes one or more audit Hamilton modules against a Registry and collects results."""

    def __init__(self, audit_modules: list[ModuleType]):
        """Initialize the runner with audit modules.

        Args:
            audit_modules: List of Hamilton modules whose final node returns an ibis Table.
        """
        self.audit_modules = audit_modules
        self._results: dict[str, ibis.expr.types.Table] = {}

    def run(self, registry: Registry) -> dict[str, ibis.expr.types.Table]:
        """Run all audit modules against the registry.

        Args:
            registry: The Registry to audit.

        Returns:
            Dict mapping audit names to ibis Tables of flagged records.
        """
        self._results = {}
        for module in self.audit_modules:
            # Derive the final variable name from the module name
            # e.g. iacs.transforms.audit.todo -> "todo"
            final_var = module.__name__.rsplit(".", 1)[-1]

            dr = driver.Driver(
                {"registry": registry}, module, adapter=base.DictResult()
            )
            result = dr.execute([final_var])
            self._results[final_var] = result[final_var]
        return self._results

    @classmethod
    def default(cls) -> "AuditRunner":
        """Create an AuditRunner with all built-in audits loaded."""
        from iacs.dataflows.audit import (
            requirement_coverage,
            traceability,
            todo,
        )

        return cls([
            requirement_coverage,
            traceability,
            todo,
        ])

    @property
    def all_passed(self) -> bool:
        """Check if all audits passed (all tables empty)."""
        return all(t.count().execute() == 0 for t in self._results.values())
