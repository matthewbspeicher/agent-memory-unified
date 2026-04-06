#!/usr/bin/env python3
"""Fix Railway API and frontend service configurations"""

import os
import json
import requests

RAILWAY_API_URL = "https://backboard.railway.app/graphql/v2"
ENVIRONMENT_ID = "1dfff0f0-d45a-4b73-91d7-adba7bbd46ed"

SERVICES = {
    "api": {
        "id": "f6d0a179-55e6-4669-a040-137871efcb25",
        "rootDirectory": "api",
        "builder": "NIXPACKS",
        "buildCommand": "composer install --no-dev --optimize-autoloader && php artisan config:cache",
    },
    "frontend": {
        "id": "1a45c141-1bc5-40a5-a641-920a3e1dfb9a",
        "rootDirectory": "frontend",
        "builder": "NIXPACKS",
        "buildCommand": "npm install && npm run build",
    },
}

def get_token():
    with open(os.path.expanduser("~/.railway/config.json")) as f:
        config = json.load(f)
    return config["user"]["token"]

def graphql_request(query, variables, token):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    response = requests.post(RAILWAY_API_URL, json={"query": query, "variables": variables}, headers=headers)

    if response.status_code != 200:
        print(f"❌ HTTP Error: {response.status_code}")
        print(response.text[:500])
        return None

    data = response.json()
    if "errors" in data:
        print(f"❌ GraphQL Errors:")
        for error in data["errors"]:
            print(f"   - {error.get('message')}")
        return None

    return data.get("data", {})

def update_service(service_name, config):
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
        "serviceId": config["id"],
        "environmentId": ENVIRONMENT_ID,
        "input": {
            "rootDirectory": config["rootDirectory"],
            "builder": config["builder"],
            "buildCommand": config["buildCommand"],
        }
    }

    token = get_token()
    print(f"🔧 Updating {service_name} service...")
    print(f"   Root: {config['rootDirectory']}")
    print(f"   Builder: {config['builder']}")
    print(f"   Build command: {config['buildCommand']}")

    result = graphql_request(query, variables, token)

    if result:
        print(f"✅ {service_name} configured\n")
        return True
    else:
        print(f"❌ {service_name} config failed\n")
        return False

def main():
    print("🔧 Fixing Railway API and Frontend configurations\n")

    for name, config in SERVICES.items():
        update_service(name, config)

    print("✅ Configuration updates complete")
    print("   Redeploy the services to apply changes:")
    print("   railway service redeploy --service=api --yes")
    print("   railway service redeploy --service=frontend --yes")

if __name__ == "__main__":
    main()
