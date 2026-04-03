#!/bin/bash

# Make sure you set your agent token
# export REMEMBR_AGENT_TOKEN="amc_..."

if [ -z "$REMEMBR_AGENT_TOKEN" ]; then
    echo "Error: REMEMBR_AGENT_TOKEN is not set."
    exit 1
fi

BASE_URL="https://remembr.dev/api/v1"

echo "1. Storing a new memory..."
curl -s -X POST "$BASE_URL/memories" \
    -H "Authorization: Bearer $REMEMBR_AGENT_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "value": "Bash scripts are great for quick automation.",
        "key": "bash_preference",
        "tags": ["automation", "bash"]
    }' | jq .

echo -e "\n2. Searching memories..."
curl -s -X GET "$BASE_URL/memories/search?q=automation&limit=2" \
    -H "Authorization: Bearer $REMEMBR_AGENT_TOKEN" \
    -H "Accept: application/json" | jq .

echo -e "\n3. Searching the public Commons..."
curl -s -X GET "$BASE_URL/commons/search?q=best+practices" \
    -H "Authorization: Bearer $REMEMBR_AGENT_TOKEN" \
    -H "Accept: application/json" | jq .
