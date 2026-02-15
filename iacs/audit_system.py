"""AuditSystem for evaluating solution quality."""

from dataclasses import dataclass, field

import ibis
import pandas as pd

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


class Audit:
    """A single check that evaluates some aspect of a solution design.

    Base class for all audits. Subclass and override the run method
    to implement custom audit logic.
    """

    def __init__(self, name: str):
        """Initialize the audit.

        Args:
            name: The name of this audit.
        """
        self.name = name

    def run(self, registry: Registry) -> AuditResult:
        """Run the audit against a registry.

        Args:
            registry: The Registry to audit.

        Returns:
            AuditResult with pass/fail status and diagnostics.
        """
        return AuditResult(passed=True)


class AuditRunner:
    """Executes one or more audits against a Registry and collects results."""

    def __init__(self, audits: list[Audit]):
        """Initialize the runner with audits.

        Args:
            audits: List of Audit instances to run.
        """
        self.audits = audits
        self._results: dict[str, AuditResult] = {}

    def run(self, registry: Registry) -> dict[str, AuditResult]:
        """Run all audits against the registry.

        Args:
            registry: The Registry to audit.

        Returns:
            Dict mapping audit names to their results.
        """
        self._results = {}
        for audit in self.audits:
            self._results[audit.name] = audit.run(registry)
        return self._results

    @property
    def all_passed(self) -> bool:
        """Check if all audits passed."""
        return all(result.passed for result in self._results.values())


class RequirementCoverageAudit(Audit):
    """Checks that requirements have solutions."""

    def __init__(self):
        super().__init__(name="requirement_coverage")

    def run(self, registry: Registry) -> AuditResult:
        """Check that all requirements have solutions.

        A requirement is covered if:
        - It has a solution of reference pointing to it, OR
        - It has child requirements (sub-requirements)

        Args:
            registry: The Registry to audit.

        Returns:
            AuditResult flagging leaf requirements without solutions.
        """
        if "requirement" not in registry.component_types:
            return AuditResult(passed=True)

        # Get unique requirement entity IDs
        req_table = registry.view("requirement")
        requirements = req_table.select("entity_id").distinct()

        if requirements.count().execute() == 0:
            return AuditResult(passed=True)

        # Find requirements that have child requirements using the parent component
        if "parent" in registry.component_types:
            parent_table = registry.view("parent")
            # Children that are requirements, select their parent (target)
            req_children = parent_table.filter(
                parent_table.entity_id.isin(requirements.entity_id)
            )
            parents_with_req_children = req_children.select(
                entity_id=req_children.target
            ).filter(
                lambda t: t.entity_id.isin(requirements.entity_id)
            ).distinct()
        else:
            parents_with_req_children = ibis.memtable({"entity_id": []}, schema={"entity_id": "string"})

        # Get solved entity IDs
        if "solution of" in registry.component_types:
            solution_table = registry.view("solution of")
            if "value" in solution_table.columns:
                solved = solution_table.select(
                    solved_id=solution_table.value
                ).distinct()
            else:
                solved = ibis.memtable({"solved_id": []}, schema={"solved_id": "string"})
        else:
            solved = ibis.memtable({"solved_id": []}, schema={"solved_id": "string"})

        # Left join to find requirements without solutions
        merged = requirements.left_join(
            solved, requirements.entity_id == solved.solved_id
        )

        # Uncovered = no solution AND no children
        uncovered = merged.filter(
            merged.solved_id.isnull()
            & ~merged.entity_id.isin(parents_with_req_children.entity_id)
        ).select("entity_id")

        uncovered_df = uncovered.execute()

        if not uncovered_df.empty:
            messages = [
                f"Requirement '{e}' has no solution."
                for e in uncovered_df["entity_id"]
            ]
            return AuditResult(
                passed=False,
                messages=messages,
                results=uncovered_df,
            )

        return AuditResult(passed=True)


class TraceabilityAudit(Audit):
    """Checks that components trace back to requirements."""

    def __init__(self):
        super().__init__(name="traceability")

    def run(self, registry: Registry) -> AuditResult:
        """Check that all entities trace to requirements.

        An entity traces to a requirement if:
        - It has a requirement component, OR
        - It has a solution of component pointing to a requirement

        Args:
            registry: The Registry to audit.

        Returns:
            AuditResult flagging orphan entities.
        """
        if not registry.component_types:
            return AuditResult(passed=True)

        # Collect all unique entity IDs via union
        tables = [
            registry.view(ct).select("entity_id").distinct()
            for ct in registry.component_types
        ]
        all_entities = ibis.union(*tables).distinct()

        # Get entities with requirement components
        if "requirement" in registry.component_types:
            req_entities = registry.view("requirement").select("entity_id").distinct()
        else:
            req_entities = ibis.memtable({"entity_id": []}, schema={"entity_id": "string"})

        # Get entities with solution of components
        if "solution of" in registry.component_types:
            solution_entities = registry.view("solution of").select("entity_id").distinct()
        else:
            solution_entities = ibis.memtable({"entity_id": []}, schema={"entity_id": "string"})

        # Orphans have neither requirement nor solution
        orphans = all_entities.filter(
            ~all_entities.entity_id.isin(req_entities.entity_id)
            & ~all_entities.entity_id.isin(solution_entities.entity_id)
        )

        orphans_df = orphans.execute()

        if not orphans_df.empty:
            messages = [
                f"Entity '{e}' does not trace to any requirement."
                for e in orphans_df["entity_id"]
            ]
            return AuditResult(
                passed=False,
                messages=messages,
                results=orphans_df,
            )

        return AuditResult(passed=True)


class TodoAudit(Audit):
    """Reports on outstanding todos."""

    def __init__(self):
        super().__init__(name="todo")

    def run(self, registry: Registry) -> AuditResult:
        """Check for outstanding todo components.

        Args:
            registry: The Registry to audit.

        Returns:
            AuditResult flagging entities with todos.
        """
        if "todo" not in registry.component_types:
            return AuditResult(passed=True)

        todo_table = registry.view("todo")

        if todo_table.count().execute() == 0:
            return AuditResult(passed=True)

        # Build results DataFrame with unique entity_ids
        results_df = todo_table.select("entity_id").distinct().execute()

        # Build messages from the todo rows
        if "value" in todo_table.columns:
            msg_df = todo_table.select("entity_id", "value").execute()
        else:
            msg_df = todo_table.select("entity_id").execute()
            msg_df["value"] = ""

        messages = [
            f"{row['entity_id']}: {row['value']}"
            for _, row in msg_df.iterrows()
        ]

        return AuditResult(
            passed=False,
            messages=messages,
            results=results_df,
        )
