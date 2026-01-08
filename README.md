# iacs - Infrastructure as Code Sketch

A browser-based application for software architects and data architects to design infrastructure using a simple YAML format.

## Features

- **Visual Infrastructure Design**: Create and visualize infrastructure components and their connections
- **YAML-Based Configuration**: Define arbitrary infrastructure using a simple, human-readable YAML format
- **Flexible Component Types**: Support for any infrastructure component type (service, database, storage, network, compute, gateway, cache, queue, or custom types)
- **Interactive Canvas**: Visual representation of your infrastructure with automatic layout
- **Export Capability**: Export your infrastructure diagrams as PNG images
- **No Backend Required**: Runs entirely in the browser

## Getting Started

Simply open `index.html` in a web browser to start using iacs.

## YAML Format

Define your infrastructure using the following YAML structure:

```yaml
name: My Infrastructure
description: Description of your infrastructure
components:
  - name: Component Name
    type: service
    properties:
      - key: value
    connections:
      - target: Other Component Name
```

### Fields

- **name** (required at root level): Name of your infrastructure
- **description** (optional): Description of your infrastructure
- **components** (required): Array of infrastructure components

### Component Fields

- **name** (required): Name of the component
- **type** (optional): Type of component (service, database, storage, network, compute, gateway, cache, queue, or any custom type)
- **properties** (optional): Array of key-value properties for the component
- **connections** (optional): Array of connections to other components

### Supported Component Types

The following types are recognized with color coding:
- `service` - Application services (green)
- `database` - Database systems (blue)
- `storage` - Storage systems (orange)
- `network` - Network components (purple)
- `compute` - Compute resources (red)
- `gateway` - Gateways and load balancers (cyan)
- `cache` - Caching systems (amber)
- `queue` - Message queues (pink)
- Any other custom type (gray)

## Example

```yaml
name: E-Commerce Platform
description: Multi-tier web application infrastructure
components:
  - name: Load Balancer
    type: gateway
    properties:
      - protocol: HTTPS
      - ssl: enabled
    connections:
      - target: Web Server
  
  - name: Web Server
    type: service
    properties:
      - runtime: Node.js
      - port: 3000
    connections:
      - target: Database
  
  - name: Database
    type: database
    properties:
      - engine: PostgreSQL
      - version: 14
```

## Use Cases

- Architecture planning and documentation
- Infrastructure proposal presentations
- Teaching and learning infrastructure concepts
- Quick infrastructure sketches and diagrams
- Documenting existing infrastructure

## Technical Details

- Pure client-side application (HTML, CSS, JavaScript)
- Custom YAML parser for infrastructure definitions
- Canvas API for rendering
- No dependencies or external libraries required

## License

This project is open source.
