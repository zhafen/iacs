"""AuditSystem for evaluating solution quality."""

from dataclasses import dataclass, field
from types import ModuleType

import ibis
import pandas as pd
from hamilton import driver, base

from iacs.registry import Registry


def _empty_results_df() -> pd.DataFrame:
    """Return an empty DataFrame for AuditResult.results."""
    return pd.DataFrame()


@dataclass
class AuditResult:
    """The outcome of running an audit.

    Attributes:
        passed: Whether the audit passed.
        messages: Diagnostic messages from the audit.
        results: DataFrame of failed records (includes entity_id column).
    """

    passed: bool
    messages: list[str] = field(default_factory=list)
    results: pd.DataFrame = field(default_factory=_empty_results_df)

    def view(self) -> ibis.expr.types.Table:
        """Return the results as an Ibis table."""
        if self.results.empty and self.results.columns.empty:
            return ibis.memtable(
                {"entity_id": []}, schema={"entity_id": "string"}
            )
        return ibis.memtable(self.results)


class AuditRunner:
    """Executes one or more audit Hamilton modules against a Registry and collects results."""

    def __init__(self, audit_modules: list[ModuleType]):
        """Initialize the runner with audit modules.

        Args:
            audit_modules: List of Hamilton modules that produce AuditResult nodes.
        """
        self.audit_modules = audit_modules
        self._results: dict[str, AuditResult] = {}

    def run(self, registry: Registry) -> dict[str, AuditResult]:
        """Run all audit modules against the registry.

        Args:
            registry: The Registry to audit.

        Returns:
            Dict mapping audit names to their results.
        """
        self._results = {}
        for module in self.audit_modules:
            dr = driver.Driver(
                {"registry": registry}, module, adapter=base.DictResult()
            )
            audit_vars = [
                v.name
                for v in dr.list_available_variables()
                if v.type == AuditResult and not v.is_external_input
            ]
            result = dr.execute(audit_vars)
            for name, value in result.items():
                self._results[name] = value
        return self._results

    @classmethod
    def default(cls) -> "AuditRunner":
        """Create an AuditRunner with all built-in audits loaded."""
        from iacs.transforms import (
            audit_requirement_coverage,
            audit_traceability,
            audit_todo,
        )

        return cls([
            audit_requirement_coverage,
            audit_traceability,
            audit_todo,
        ])

    @property
    def all_passed(self) -> bool:
        """Check if all audits passed."""
        return all(result.passed for result in self._results.values())
