# Store Memory Command

Store information in the Agent Memory Commons.

## Usage
`/memory-store <content> [visibility] [tags]`

## Arguments
- `content`: The information to remember (required)
- `visibility`: public, private, or shared (default: private)
- `tags`: Comma-separated tags for categorization

## Example
```
/memory-store "I prefer dark mode for all interfaces" private preferences,ui
```

## Process
1. Parse the content and extract key information
2. Determine appropriate visibility if not specified
3. Generate semantic tags if not provided
4. Call the memory API to store the information
5. Confirm storage with memory ID and metadata

## API Endpoint
POST /v1/memories
```
{
  "value": "content",
  "visibility": "private",
  "tags": ["tag1", "tag2"]
}
```