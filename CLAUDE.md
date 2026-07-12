# CLAUDE.md - AI Assistant Instructions for iacs

## Project Overview

iacs (Infrastructure-as-Code Sketch) is an ECS-based system for documenting and designing infrastructure. It uses an Entity-Component-System framework for modeling infrastructure solutions.

## Development Guidelines

### Git Workflow

- Use `uv` for Python package management.

### Testing

- Run tests with `uv run pytest`.
- Follow TDD approach: write tests first, then implement.

### Code Style

- Keep solutions simple and focused.
- Avoid over-engineering - only make changes that are directly requested.

## Key Concepts

- **Entity-Centered Format**: Human-friendly EC file format for defining entities and their components.
- **Component-Centered Format (Registry)**: Internal format with one table per component type.
- **Audits**: Checks that evaluate solution quality (RequirementCoverageAudit, TraceabilityAudit, TodoAudit).
- **"solution of" component**: A directed_relation component indicating that an entity solves/fulfills a requirement.
