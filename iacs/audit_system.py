"""AuditSystem for evaluating solution quality."""

from dataclasses import dataclass, field

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
    """Checks that requirements have implementing solutions."""

    def __init__(self):
        super().__init__(name="requirement_coverage")

    def run(self, registry: Registry) -> AuditResult:
        """Check that all requirements have implementations.

        A requirement is covered if:
        - It has an implements reference pointing to it, OR
        - It has child requirements (sub-requirements)

        Args:
            registry: The Registry to audit.

        Returns:
            AuditResult flagging leaf requirements without implementations.
        """
        if "requirement" not in registry.component_types:
            return AuditResult(passed=True)

        # Get requirements as DataFrame with entity_id column
        requirement_table = registry.view("requirement")
        requirements_df = pd.DataFrame({
            "entity_id": requirement_table.index.get_level_values("entity_id").unique()
        })

        if requirements_df.empty:
            return AuditResult(passed=True)

        # Find requirements that have child requirements
        # A child requirement has an entity_id starting with "{parent_id}."
        requirement_ids = requirements_df["entity_id"].tolist()

        def has_child_requirement(entity_id: str) -> bool:
            prefix = entity_id + "."
            return any(rid.startswith(prefix) for rid in requirement_ids)

        requirements_df["has_children"] = requirements_df["entity_id"].apply(
            has_child_requirement
        )

        # Get implemented entity IDs as DataFrame
        if "implements" in registry.component_types:
            implements_table = registry.view("implements")
            if "value" in implements_table.columns:
                implemented_df = pd.DataFrame({
                    "implemented_id": implements_table["value"].unique()
                })
            else:
                implemented_df = pd.DataFrame({"implemented_id": []})
        else:
            implemented_df = pd.DataFrame({"implemented_id": []})

        # Left join to find requirements without implements
        merged = requirements_df.merge(
            implemented_df,
            left_on="entity_id",
            right_on="implemented_id",
            how="left",
        )

        # Uncovered = no implements AND no children
        uncovered_df = merged[
            merged["implemented_id"].isna() & ~merged["has_children"]
        ][["entity_id"]].copy()

        if not uncovered_df.empty:
            messages = [
                f"Requirement '{e}' has no implementation."
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
        - It has an implements component pointing to a requirement

        Args:
            registry: The Registry to audit.

        Returns:
            AuditResult flagging orphan entities.
        """
        if not registry.component_types:
            return AuditResult(passed=True)

        # Collect all entity IDs into a DataFrame
        all_entity_ids = []
        for component_type in registry.component_types:
            table = registry.view(component_type)
            all_entity_ids.extend(table.index.get_level_values("entity_id").tolist())
        all_entities_df = pd.DataFrame({"entity_id": pd.Series(all_entity_ids).unique()})

        # Get entities with requirement components
        if "requirement" in registry.component_types:
            req_table = registry.view("requirement")
            req_entities_df = pd.DataFrame({
                "entity_id": req_table.index.get_level_values("entity_id").unique(),
                "has_requirement": True,
            })
        else:
            req_entities_df = pd.DataFrame({"entity_id": [], "has_requirement": []})

        # Get entities with implements components
        if "implements" in registry.component_types:
            impl_table = registry.view("implements")
            impl_entities_df = pd.DataFrame({
                "entity_id": impl_table.index.get_level_values("entity_id").unique(),
                "has_implements": True,
            })
        else:
            impl_entities_df = pd.DataFrame({"entity_id": [], "has_implements": []})

        # Join to find entities that have neither
        merged = all_entities_df.merge(req_entities_df, on="entity_id", how="left")
        merged = merged.merge(impl_entities_df, on="entity_id", how="left")

        # Orphans have neither requirement nor implements
        orphans_df = merged[
            merged["has_requirement"].isna() & merged["has_implements"].isna()
        ][["entity_id"]].copy()

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

        if todo_table.empty:
            return AuditResult(passed=True)

        # Build results DataFrame with entity_id
        results_df = pd.DataFrame({
            "entity_id": todo_table.index.get_level_values("entity_id").unique()
        })

        # Build messages from the DataFrame
        messages = []
        for entity_id, component_index in todo_table.index:
            todo_value = (
                todo_table.loc[(entity_id, component_index), "value"]
                if "value" in todo_table.columns
                else ""
            )
            messages.append(f"{entity_id}: {todo_value}")

        return AuditResult(
            passed=False,
            messages=messages,
            results=results_df,
        )
