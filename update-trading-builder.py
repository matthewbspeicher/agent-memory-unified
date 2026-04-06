#!/usr/bin/env python3
"""Update Railway trading service to use Dockerfile"""

import os
import sys
import requests
import json

RAILWAY_API_URL = "https://backboard.railway.app/graphql/v2"
SERVICE_ID = "b44f6d92-76f4-4149-950f-ba13b0e6c12d"  # trading service

def get_token():
    token = os.getenv("RAILWAY_API_TOKEN")
    if not token:
        print("❌ Error: RAILWAY_API_TOKEN not set")
        print("   Run: export RAILWAY_API_TOKEN=$(railway whoami --json | jq -r .token)")
        sys.exit(1)
    return token

def graphql_request(query, variables, token):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    payload = {"query": query, "variables": variables}
    print(f"\n📤 Sending request:")
    print(f"   Query: {query[:100]}...")
    print(f"   Variables: {json.dumps(variables, indent=2)}")

    response = requests.post(RAILWAY_API_URL, json=payload, headers=headers)

    print(f"\n📥 Response status: {response.status_code}")
    print(f"   Response body: {response.text[:500]}")

    if response.status_code != 200:
        print(f"❌ HTTP Error: {response.status_code}")
        return None

    data = response.json()
    if "errors" in data:
        print(f"❌ GraphQL Errors:")
        for error in data["errors"]:
            print(f"   - {error.get('message')}")
            if 'extensions' in error:
                print(f"     Extensions: {json.dumps(error['extensions'], indent=6)}")
        return None

    return data.get("data", {})

def update_service():
    # Update service instance with Dockerfile settings
    query = """
    mutation UpdateServiceInstance($serviceId: String!, $environmentId: String!, $input: ServiceInstanceUpdateInput!) {
        serviceInstanceUpdate(
            serviceId: $serviceId
            environmentId: $environmentId
            input: $input
        )
    }
    """

    variables = {
        "serviceId": SERVICE_ID,
        "environmentId": "1dfff0f0-d45a-4b73-91d7-adba7bbd46ed",
        "input": {
            "rootDirectory": "",  # Empty string = repo root
            "dockerfilePath": "Dockerfile.trading",
            "builder": "RAILPACK"  # RAILPACK auto-detects Dockerfile
        }
    }

    token = get_token()
    print(f"🔧 Updating trading service configuration...")
    print(f"   Service ID: {SERVICE_ID}")
    print(f"   Target: RAILPACK builder with Dockerfile.trading from repo root")

    result = graphql_request(query, variables, token)

    if result:
        print(f"\n✅ Service updated successfully")
        print(f"   Result: {json.dumps(result, indent=2)}")
        return True
    else:
        print(f"\n❌ Failed to update service")
        return False

if __name__ == "__main__":
    success = update_service()
    sys.exit(0 if success else 1)
