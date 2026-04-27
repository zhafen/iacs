# iacs

Infrastructure-as-Code Sketch — an ECS-based system for documenting and designing infrastructure.

## Install

```bash
pip install iacs
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv add iacs
```

## Usage

Define infrastructure entities in YAML:

```yaml
my_service:
  description: A web service
  requirement: Must handle 1000 req/s

my_deployment:
  description: Kubernetes deployment for my_service
  solution of: my_service
```

Run audits to evaluate your design:

```python
import iacs

registry = iacs.load("infrastructure.yaml")
audit = iacs.RequirementCoverageAudit(registry)
print(audit.report())
```
