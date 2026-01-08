// Simple YAML parser for iacs
// Supports the subset of YAML needed for infrastructure definitions

const jsyaml = {
    load: function(yamlString) {
        const lines = yamlString.split('\n');
        const result = {};
        let indentStack = [{ level: -1, obj: result }];
        
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            const trimmedLine = line.trim();
            
            // Skip empty lines and comments
            if (!trimmedLine || trimmedLine.startsWith('#')) {
                continue;
            }
            
            // Calculate indentation level
            const indent = line.search(/\S/);
            
            // Pop stack to find correct parent
            while (indentStack.length > 1 && indent <= indentStack[indentStack.length - 1].level) {
                indentStack.pop();
            }
            
            const parent = indentStack[indentStack.length - 1].obj;
            
            // Handle array items
            if (trimmedLine.startsWith('- ')) {
                const content = trimmedLine.substring(2).trim();
                
                if (content.includes(':')) {
                    // Array of objects
                    const [key, value] = this.splitKeyValue(content);
                    const newItem = {};
                    newItem[key] = this.parseValue(value);
                    
                    // Find the array to add to
                    const lastKey = indentStack[indentStack.length - 1].lastKey;
                    if (lastKey && parent[lastKey] && Array.isArray(parent[lastKey])) {
                        parent[lastKey].push(newItem);
                        indentStack.push({ level: indent, obj: newItem, lastKey: key });
                    } else if (Array.isArray(parent)) {
                        // Parent itself is an array
                        parent.push(newItem);
                        indentStack.push({ level: indent, obj: newItem, lastKey: key });
                    }
                } else {
                    // Simple array item
                    const lastKey = indentStack[indentStack.length - 1].lastKey;
                    if (lastKey && parent[lastKey] && Array.isArray(parent[lastKey])) {
                        parent[lastKey].push(this.parseValue(content));
                    } else if (Array.isArray(parent)) {
                        // Parent itself is an array
                        parent.push(this.parseValue(content));
                    }
                }
            } else if (trimmedLine.includes(':')) {
                const [key, value] = this.splitKeyValue(trimmedLine);
                
                if (value === '') {
                    // New object or array
                    const nextLine = i + 1 < lines.length ? lines[i + 1] : '';
                    const nextTrimmed = nextLine.trim();
                    
                    if (nextTrimmed.startsWith('- ')) {
                        // It's an array
                        parent[key] = [];
                        indentStack.push({ level: indent, obj: parent, lastKey: key });
                    } else {
                        // It's an object
                        parent[key] = {};
                        indentStack.push({ level: indent, obj: parent[key], lastKey: key });
                    }
                } else {
                    // Key-value pair
                    parent[key] = this.parseValue(value);
                    indentStack[indentStack.length - 1].lastKey = key;
                }
            }
        }
        
        return result;
    },
    
    splitKeyValue: function(line) {
        const colonIndex = line.indexOf(':');
        if (colonIndex === -1) {
            return [line, ''];
        }
        const key = line.substring(0, colonIndex).trim();
        const value = line.substring(colonIndex + 1).trim();
        return [key, value];
    },
    
    parseValue: function(value) {
        // Remove quotes
        if ((value.startsWith('"') && value.endsWith('"')) || 
            (value.startsWith("'") && value.endsWith("'"))) {
            return value.substring(1, value.length - 1);
        }
        
        // Parse numbers - strict validation (allows integers and proper decimals)
        if (/^-?\d+(\.\d+)?$/.test(value)) {
            return parseFloat(value);
        }
        
        // Parse booleans
        if (value === 'true') return true;
        if (value === 'false') return false;
        if (value === 'null') return null;
        
        return value;
    }
};
