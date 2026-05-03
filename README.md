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

## Development

### Setup

```bash
git clone https://github.com/zhafen/iacs
cd iacs
uv sync
```

Run the tests:

```bash
uv run pytest
```

### Docs

Generate and serve the docs locally:

```bash
uv run mkdocs serve
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.
