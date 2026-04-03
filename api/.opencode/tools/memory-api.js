// Custom tool for interacting with Agent Memory Commons API

export const MemoryAPITool = async ({ project, client, $, directory, worktree }) => {
  const API_BASE = "https://remembr.dev/api/v1"
  
  return {
    tool: {
      "memory-search": {
        description: "Search memories in Agent Memory Commons",
        args: {
          query: { type: "string", description: "Search query" },
          visibility: { type: "string", description: "Filter by visibility (public/private/shared)", optional: true },
          limit: { type: "number", description: "Max results to return", optional: true }
        },
        async execute(args, context) {
          try {
            const params = new URLSearchParams({
              q: args.query,
              ...(args.visibility && { visibility: args.visibility }),
              ...(args.limit && { limit: args.limit.toString() })
            })
            
            const response = await fetch(`${API_BASE}/memories/search?${params}`, {
              headers: {
                'Authorization': `Bearer ${process.env.AGENT_MEMORY_TOKEN || ''}`,
                'Content-Type': 'application/json'
              }
            })
            
            if (!response.ok) {
              throw new Error(`API error: ${response.status}`)
            }
            
            const data = await response.json()
            return JSON.stringify(data, null, 2)
          } catch (error) {
            return `Error searching memories: ${error.message}`
          }
        }
      },
      
      "memory-store": {
        description: "Store a memory in Agent Memory Commons",
        args: {
          content: { type: "string", description: "Content to remember" },
          visibility: { type: "string", description: "Visibility (public/private/shared)", optional: true },
          tags: { type: "string", description: "Comma-separated tags", optional: true }
        },
        async execute(args, context) {
          try {
            const body = {
              value: args.content,
              visibility: args.visibility || 'private',
              ...(args.tags && { tags: args.tags.split(',').map(t => t.trim()) })
            }
            
            const response = await fetch(`${API_BASE}/memories`, {
              method: 'POST',
              headers: {
                'Authorization': `Bearer ${process.env.AGENT_MEMORY_TOKEN || ''}`,
                'Content-Type': 'application/json'
              },
              body: JSON.stringify(body)
            })
            
            if (!response.ok) {
              throw new Error(`API error: ${response.status}`)
            }
            
            const data = await response.json()
            return `Memory stored successfully!\nID: ${data.id}\nTags: ${data.tags?.join(', ') || 'none'}\nVisibility: ${data.visibility}`
          } catch (error) {
            return `Error storing memory: ${error.message}`
          }
        }
      },
      
      "memory-get": {
        description: "Get a specific memory by ID",
        args: {
          id: { type: "string", description: "Memory ID" }
        },
        async execute(args, context) {
          try {
            const response = await fetch(`${API_BASE}/memories/${args.id}`, {
              headers: {
                'Authorization': `Bearer ${process.env.AGENT_MEMORY_TOKEN || ''}`,
                'Content-Type': 'application/json'
              }
            })
            
            if (!response.ok) {
              throw new Error(`API error: ${response.status}`)
            }
            
            const data = await response.json()
            return JSON.stringify(data, null, 2)
          } catch (error) {
            return `Error getting memory: ${error.message}`
          }
        }
      }
    }
  }
}