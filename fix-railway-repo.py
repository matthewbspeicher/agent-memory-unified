#!/usr/bin/env python3
"""Update Railway services to point to agent-memory-unified repo"""

import os
import sys
import requests

RAILWAY_API_URL = "https://backboard.railway.app/graphql/v2"
PROJECT_ID = "21c3f323-784d-4ec4-8828-1bc190723066"
NEW_REPO = "matthewbspeicher/agent-memory-unified"

SERVICES = {
    "api": "f6d0a179-55e6-4669-a040-137871efcb25",
    "trading": "b44f6d92-76f4-4149-950f-ba13b0e6c12d",
    "frontend": "1a45c141-1bc5-40a5-a641-920a3e1dfb9a",
}

def get_api_token():
    token = os.getenv("RAILWAY_API_TOKEN")
    if not token:
        print("❌ Error: RAILWAY_API_TOKEN not set")
        sys.exit(1)
    return token

def graphql_request(query, variables, token):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    response = requests.post(RAILWAY_API_URL, json={"query": query, "variables": variables}, headers=headers)
    if response.status_code != 200:
        print(f"❌ API failed: {response.status_code}")
        print(response.text)
        sys.exit(1)
    data = response.json()
    if "errors" in data:
        print(f"❌ GraphQL errors:")
        for error in data["errors"]:
            print(f"  - {error.get('message')}")
        sys.exit(1)
    return data.get("data", {})

def update_service_repo(service_id, service_name, token):
    query = """
    mutation ServiceConnect($id: String!, $input: ServiceConnectInput!) {
        serviceConnect(id: $id, input: $input) {
            id
            name
        }
    }
    """
    variables = {
        "id": service_id,
        "input": {
            "repo": NEW_REPO
        }
    }
    print(f"📝 Updating {service_name} to {NEW_REPO}...")
    graphql_request(query, variables, token)
    print(f"✅ {service_name} updated")

def main():
    print(f"🔧 Updating Railway services to {NEW_REPO}\n")
    token = get_api_token()

    for name, service_id in SERVICES.items():
        update_service_repo(service_id, name, token)

    print(f"\n✅ All services updated!")
    print(f"\n🚀 Triggering redeployments...")
    print(f"   Run: cd /opt/homebrew/var/www/agent-memory-unified && railway service redeploy --yes")

if __name__ == "__main__":
    main()
