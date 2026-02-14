"""AuditSystem for evaluating solution quality."""

from dataclasses import dataclass, field

from iacs.registry import Registry


@dataclass
class AuditResult:
    """The outcome of running an audit.

    Attributes:
        passed: Whether the audit passed.
        messages: Diagnostic messages from the audit.
        entities: Entity IDs flagged by the audit.
    """

    passed: bool
    messages: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)


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

        Args:
            registry: The Registry to audit.

        Returns:
            AuditResult flagging requirements without implementations.
        """
        # Get all entities with requirement components
        if "requirement" not in registry.component_types:
            return AuditResult(passed=True)

        requirement_table = registry.view("requirement")
        requirement_entities = set(requirement_table.index.get_level_values("entity_id"))

        # Get all entities that are implemented
        implemented_entities: set[str] = set()
        if "implements" in registry.component_types:
            implements_table = registry.view("implements")
            if "value" in implements_table.columns:
                implemented_entities = set(implements_table["value"].tolist())

        # Find uncovered requirements
        uncovered = requirement_entities - implemented_entities

        if uncovered:
            return AuditResult(
                passed=False,
                messages=[f"Requirement '{e}' has no implementation." for e in uncovered],
                entities=list(uncovered),
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

        # Collect all entity IDs
        all_entities: set[str] = set()
        for component_type in registry.component_types:
            table = registry.view(component_type)
            all_entities.update(table.index.get_level_values("entity_id"))

        # Entities with requirement components are OK
        entities_with_requirements: set[str] = set()
        if "requirement" in registry.component_types:
            req_table = registry.view("requirement")
            entities_with_requirements = set(
                req_table.index.get_level_values("entity_id")
            )

        # Entities with implements components are OK
        entities_with_implements: set[str] = set()
        if "implements" in registry.component_types:
            impl_table = registry.view("implements")
            entities_with_implements = set(
                impl_table.index.get_level_values("entity_id")
            )

        # Find orphans
        traced_entities = entities_with_requirements | entities_with_implements
        orphans = all_entities - traced_entities

        if orphans:
            return AuditResult(
                passed=False,
                messages=[f"Entity '{e}' does not trace to any requirement." for e in orphans],
                entities=list(orphans),
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
        entities_with_todos = list(set(todo_table.index.get_level_values("entity_id")))

        if not entities_with_todos:
            return AuditResult(passed=True)

        # Build messages with todo content
        messages = []
        for idx, row in todo_table.iterrows():
            entity_id = idx[0]  # First level of multi-index
            todo_value = row.get("value", "")
            messages.append(f"{entity_id}: {todo_value}")

        return AuditResult(
            passed=False,
            messages=messages,
            entities=entities_with_todos,
        )
