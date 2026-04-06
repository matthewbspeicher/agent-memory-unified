#!/usr/bin/env python3
"""Set root directories for Railway services"""

import os
import sys
import requests

RAILWAY_API_URL = "https://backboard.railway.app/graphql/v2"

SERVICES = {
    "api": {"id": "f6d0a179-55e6-4669-a040-137871efcb25", "root": "api"},
    "trading": {"id": "b44f6d92-76f4-4149-950f-ba13b0e6c12d", "root": "trading"},
    "frontend": {"id": "1a45c141-1bc5-40a5-a641-920a3e1dfb9a", "root": "frontend"},
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
        return None
    data = response.json()
    if "errors" in data:
        print(f"❌ GraphQL errors:")
        for error in data["errors"]:
            print(f"  - {error.get('message')}")
        return None
    return data.get("data", {})

def set_service_config(service_id, service_name, root_dir, token):
    query = """
    mutation ServiceUpdate($id: String!, $input: ServiceUpdateInput!) {
        serviceUpdate(id: $id, input: $input) {
            id
            name
        }
    }
    """
    variables = {
        "id": service_id,
        "input": {
            "rootDirectory": root_dir,
            "region": "us-east"
        }
    }
    print(f"📝 Configuring {service_name}:")
    print(f"   - Root directory: {root_dir}")
    print(f"   - Region: us-east")
    result = graphql_request(query, variables, token)
    if result:
        print(f"✅ {service_name} configured")
        return True
    else:
        print(f"⚠️  {service_name} config failed (might need dashboard)")
    return False

def trigger_redeploy(service_id, service_name, token):
    query = """
    mutation ServiceInstanceRedeploy($serviceId: String!, $environmentId: String!) {
        serviceInstanceRedeploy(serviceId: $serviceId, environmentId: $environmentId)
    }
    """
    variables = {
        "serviceId": service_id,
        "environmentId": "1dfff0f0-d45a-4b73-91d7-adba7bbd46ed"
    }
    print(f"🚀 Redeploying {service_name}...")
    result = graphql_request(query, variables, token)
    if result:
        print(f"✅ {service_name} redeployed")
        return True
    return False

def main():
    print("🔧 Configuring Railway Services (Root + Region)\n")
    token = get_api_token()

    for name, config in SERVICES.items():
        service_id = config["id"]
        root_dir = config["root"]

        if set_service_config(service_id, name, root_dir, token):
            trigger_redeploy(service_id, name, token)
        print()

    print("✅ All services configured for us-east!")
    print("\n📊 Monitor builds at:")
    print("   https://railway.com/project/21c3f323-784d-4ec4-8828-1bc190723066")

if __name__ == "__main__":
    main()
