// Infrastructure as Code Sketch - Main Application Logic

// Polyfill for roundRect (for older browsers)
if (!CanvasRenderingContext2D.prototype.roundRect) {
    CanvasRenderingContext2D.prototype.roundRect = function(x, y, width, height, radii) {
        const radius = typeof radii === 'number' ? radii : radii[0];
        this.moveTo(x + radius, y);
        this.lineTo(x + width - radius, y);
        this.arcTo(x + width, y, x + width, y + radius, radius);
        this.lineTo(x + width, y + height - radius);
        this.arcTo(x + width, y + height, x + width - radius, y + height, radius);
        this.lineTo(x + radius, y + height);
        this.arcTo(x, y + height, x, y + height - radius, radius);
        this.lineTo(x, y + radius);
        this.arcTo(x, y, x + radius, y, radius);
        return this;
    };
}

class InfrastructureDesigner {
    constructor() {
        this.canvas = document.getElementById('infraCanvas');
        this.ctx = this.canvas.getContext('2d');
        this.yamlEditor = document.getElementById('yamlEditor');
        this.errorMessage = document.getElementById('errorMessage');
        this.canvasInfo = document.getElementById('canvasInfo');
        
        this.infrastructure = null;
        this.components = [];
        this.scale = 1;
        this.offsetX = 0;
        this.offsetY = 0;
        
        this.initializeCanvas();
        this.setupEventListeners();
        this.showWelcomeMessage();
    }
    
    initializeCanvas() {
        // Set canvas size to match display size
        const rect = this.canvas.getBoundingClientRect();
        this.canvas.width = rect.width * window.devicePixelRatio;
        this.canvas.height = rect.height * window.devicePixelRatio;
        this.ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    }
    
    setupEventListeners() {
        document.getElementById('renderBtn').addEventListener('click', () => this.renderInfrastructure());
        document.getElementById('clearBtn').addEventListener('click', () => this.clearEditor());
        document.getElementById('loadExample').addEventListener('click', () => this.loadExample());
        document.getElementById('exportBtn').addEventListener('click', () => this.exportCanvas());
        
        // Handle window resize
        window.addEventListener('resize', () => {
            this.initializeCanvas();
            if (this.infrastructure) {
                this.drawInfrastructure();
            }
        });
    }
    
    showWelcomeMessage() {
        this.canvasInfo.textContent = 'Load an example or write your own YAML to visualize infrastructure';
    }
    
    clearEditor() {
        this.yamlEditor.value = '';
        this.clearError();
        this.clearCanvas();
        this.showWelcomeMessage();
    }
    
    loadExample() {
        const exampleYaml = `name: E-Commerce Platform
description: Multi-tier web application infrastructure
components:
  - name: Load Balancer
    type: gateway
    properties:
      - protocol: HTTPS
      - ssl: enabled
    connections:
      - target: Web Server 1
      - target: Web Server 2
  
  - name: Web Server 1
    type: service
    properties:
      - runtime: Node.js
      - port: 3000
    connections:
      - target: Application Server
      - target: Cache
  
  - name: Web Server 2
    type: service
    properties:
      - runtime: Node.js
      - port: 3000
    connections:
      - target: Application Server
      - target: Cache
  
  - name: Application Server
    type: compute
    properties:
      - framework: Express
      - instances: 3
    connections:
      - target: Database
      - target: Message Queue
  
  - name: Cache
    type: cache
    properties:
      - engine: Redis
      - memory: 4GB
  
  - name: Database
    type: database
    properties:
      - engine: PostgreSQL
      - version: 14
      - replicas: 2
  
  - name: Message Queue
    type: queue
    properties:
      - service: RabbitMQ
    connections:
      - target: Worker Service
  
  - name: Worker Service
    type: service
    properties:
      - runtime: Python
      - workers: 5
    connections:
      - target: Storage
  
  - name: Storage
    type: storage
    properties:
      - type: Object Storage
      - capacity: 1TB`;
        
        this.yamlEditor.value = exampleYaml;
        this.clearError();
    }
    
    renderInfrastructure() {
        const yamlText = this.yamlEditor.value.trim();
        
        if (!yamlText) {
            this.showError('Please enter YAML configuration');
            return;
        }
        
        try {
            this.infrastructure = jsyaml.load(yamlText);
            this.validateInfrastructure();
            this.clearError();
            this.layoutComponents();
            this.drawInfrastructure();
            this.canvasInfo.textContent = `Rendered: ${this.infrastructure.name || 'Infrastructure'}`;
        } catch (error) {
            this.showError(`YAML Parse Error: ${error.message}`);
        }
    }
    
    validateInfrastructure() {
        if (!this.infrastructure.components || !Array.isArray(this.infrastructure.components)) {
            throw new Error('Infrastructure must have a "components" array');
        }
        
        if (this.infrastructure.components.length === 0) {
            throw new Error('Infrastructure must have at least one component');
        }
        
        // Validate each component has a name
        this.infrastructure.components.forEach((comp, idx) => {
            if (!comp.name) {
                throw new Error(`Component at index ${idx} is missing a name`);
            }
        });
    }
    
    layoutComponents() {
        const components = this.infrastructure.components;
        const canvasWidth = this.canvas.getBoundingClientRect().width;
        const canvasHeight = this.canvas.getBoundingClientRect().height;
        
        // Create a simple grid layout
        const cols = Math.ceil(Math.sqrt(components.length));
        const rows = Math.ceil(components.length / cols);
        
        const cellWidth = canvasWidth / (cols + 1);
        const cellHeight = canvasHeight / (rows + 1);
        
        this.components = components.map((comp, idx) => {
            const col = idx % cols;
            const row = Math.floor(idx / cols);
            
            return {
                ...comp,
                x: cellWidth * (col + 1),
                y: cellHeight * (row + 1),
                width: 120,
                height: 80
            };
        });
    }
    
    drawInfrastructure() {
        this.clearCanvas();
        
        // Draw connections first (so they appear behind components)
        this.drawConnections();
        
        // Draw components
        this.components.forEach(comp => this.drawComponent(comp));
        
        // Draw title
        this.drawTitle();
    }
    
    drawTitle() {
        const ctx = this.ctx;
        const title = this.infrastructure.name || 'Infrastructure';
        
        ctx.font = 'bold 20px sans-serif';
        ctx.fillStyle = '#667eea';
        ctx.textAlign = 'center';
        ctx.fillText(title, this.canvas.getBoundingClientRect().width / 2, 30);
    }
    
    drawConnections() {
        const ctx = this.ctx;
        
        this.components.forEach(comp => {
            if (comp.connections && Array.isArray(comp.connections)) {
                comp.connections.forEach(conn => {
                    const targetName = conn.target || conn;
                    const target = this.components.find(c => c.name === targetName);
                    
                    if (target) {
                        // Draw arrow from comp to target
                        ctx.strokeStyle = '#aaa';
                        ctx.lineWidth = 2;
                        ctx.setLineDash([5, 5]);
                        
                        ctx.beginPath();
                        ctx.moveTo(comp.x, comp.y);
                        ctx.lineTo(target.x, target.y);
                        ctx.stroke();
                        
                        // Draw arrow head
                        const angle = Math.atan2(target.y - comp.y, target.x - comp.x);
                        const arrowLength = 10;
                        
                        ctx.setLineDash([]);
                        ctx.beginPath();
                        ctx.moveTo(target.x, target.y);
                        ctx.lineTo(
                            target.x - arrowLength * Math.cos(angle - Math.PI / 6),
                            target.y - arrowLength * Math.sin(angle - Math.PI / 6)
                        );
                        ctx.moveTo(target.x, target.y);
                        ctx.lineTo(
                            target.x - arrowLength * Math.cos(angle + Math.PI / 6),
                            target.y - arrowLength * Math.sin(angle + Math.PI / 6)
                        );
                        ctx.stroke();
                    }
                });
            }
        });
        
        ctx.setLineDash([]);
    }
    
    drawComponent(comp) {
        const ctx = this.ctx;
        const typeColors = {
            service: '#4CAF50',
            database: '#2196F3',
            storage: '#FF9800',
            network: '#9C27B0',
            compute: '#F44336',
            gateway: '#00BCD4',
            cache: '#FFC107',
            queue: '#E91E63',
            default: '#607D8B'
        };
        
        const color = typeColors[comp.type] || typeColors.default;
        
        // Draw component box with shadow
        ctx.shadowColor = 'rgba(0, 0, 0, 0.2)';
        ctx.shadowBlur = 10;
        ctx.shadowOffsetX = 2;
        ctx.shadowOffsetY = 2;
        
        // Draw rounded rectangle
        const x = comp.x - comp.width / 2;
        const y = comp.y - comp.height / 2;
        const radius = 8;
        
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.roundRect(x, y, comp.width, comp.height, radius);
        ctx.fill();
        
        // Reset shadow
        ctx.shadowColor = 'transparent';
        ctx.shadowBlur = 0;
        ctx.shadowOffsetX = 0;
        ctx.shadowOffsetY = 0;
        
        // Draw border
        ctx.strokeStyle = this.darkenColor(color, 20);
        ctx.lineWidth = 2;
        ctx.stroke();
        
        // Draw component name
        ctx.fillStyle = 'white';
        ctx.font = 'bold 14px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        
        // Wrap text if too long
        const maxWidth = comp.width - 10;
        const words = comp.name.split(' ');
        let lines = [];
        let currentLine = words[0];
        
        for (let i = 1; i < words.length; i++) {
            const testLine = currentLine + ' ' + words[i];
            const metrics = ctx.measureText(testLine);
            if (metrics.width > maxWidth) {
                lines.push(currentLine);
                currentLine = words[i];
            } else {
                currentLine = testLine;
            }
        }
        lines.push(currentLine);
        
        // Draw lines
        const lineHeight = 16;
        const startY = comp.y - (lines.length - 1) * lineHeight / 2;
        lines.forEach((line, idx) => {
            ctx.fillText(line, comp.x, startY + idx * lineHeight - 5);
        });
        
        // Draw type
        ctx.font = '11px sans-serif';
        ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
        ctx.fillText(comp.type || 'component', comp.x, comp.y + 15);
    }
    
    darkenColor(hex, percent) {
        // Convert hex to RGB
        const num = parseInt(hex.replace('#', ''), 16);
        const r = (num >> 16) - percent;
        const g = ((num >> 8) & 0x00FF) - percent;
        const b = (num & 0x0000FF) - percent;
        
        return `rgb(${Math.max(0, r)}, ${Math.max(0, g)}, ${Math.max(0, b)})`;
    }
    
    clearCanvas() {
        const rect = this.canvas.getBoundingClientRect();
        this.ctx.clearRect(0, 0, rect.width, rect.height);
    }
    
    showError(message) {
        this.errorMessage.textContent = message;
        this.errorMessage.classList.add('show');
    }
    
    clearError() {
        this.errorMessage.textContent = '';
        this.errorMessage.classList.remove('show');
    }
    
    exportCanvas() {
        if (!this.infrastructure) {
            this.showError('Please render infrastructure before exporting');
            return;
        }
        
        const link = document.createElement('a');
        link.download = `${this.infrastructure.name || 'infrastructure'}.png`;
        link.href = this.canvas.toDataURL();
        link.click();
    }
}

// Initialize the application when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new InfrastructureDesigner();
});
