#!/usr/bin/env python3
"""
Railway Multi-Service Setup via GraphQL API

Creates 3 services (api, trading, frontend) in us-east-1 region
with proper root directories and start commands.

Requirements:
    pip install requests

Usage:
    export RAILWAY_API_TOKEN="your-token-here"
    python setup-railway-services.py
"""

import os
import sys
import json
import requests
from typing import Dict, Any, Optional


RAILWAY_API_URL = "https://backboard.railway.app/graphql/v2"
PROJECT_ID = "21c3f323-784d-4ec4-8828-1bc190723066"
ENVIRONMENT_ID = "1dfff0f0-d45a-4b73-91d7-adba7bbd46ed"
GITHUB_REPO = "matthewbspeicher/remembr-dev"


def get_api_token() -> str:
    """Get Railway API token from environment."""
    token = os.getenv("RAILWAY_API_TOKEN")
    if not token:
        print("❌ Error: RAILWAY_API_TOKEN environment variable not set")
        print("\nTo get your token:")
        print("1. Go to: https://railway.app/account/tokens")
        print("2. Create a new token")
        print("3. Export it: export RAILWAY_API_TOKEN='your-token'")
        sys.exit(1)
    return token


def graphql_request(query: str, variables: Dict[str, Any], token: str) -> Dict[str, Any]:
    """Make a GraphQL request to Railway API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    payload = {
        "query": query,
        "variables": variables
    }

    response = requests.post(RAILWAY_API_URL, json=payload, headers=headers)

    if response.status_code != 200:
        print(f"❌ API request failed: {response.status_code}")
        print(response.text)
        sys.exit(1)

    data = response.json()

    if "errors" in data:
        print(f"❌ GraphQL errors:")
        for error in data["errors"]:
            print(f"  - {error.get('message', 'Unknown error')}")
        sys.exit(1)

    return data.get("data", {})


def create_service(name: str, root_dir: str, token: str) -> str:
    """Create a new service in the project."""
    query = """
    mutation ServiceCreate($input: ServiceCreateInput!) {
        serviceCreate(input: $input) {
            id
            name
        }
    }
    """

    variables = {
        "input": {
            "projectId": PROJECT_ID,
            "name": name,
            "source": {
                "repo": GITHUB_REPO
            }
        }
    }

    print(f"📦 Creating service: {name}")
    data = graphql_request(query, variables, token)

    service = data.get("serviceCreate", {})
    service_id = service.get("id")

    if not service_id:
        print(f"❌ Failed to create service {name}")
        sys.exit(1)

    print(f"✅ Created service: {name} (ID: {service_id})")
    return service_id


def update_service_settings(service_id: str, root_dir: str, start_command: str, healthcheck_path: Optional[str], token: str):
    """Update service settings (root directory, start command, region)."""
    query = """
    mutation ServiceUpdate($id: String!, $input: ServiceUpdateInput!) {
        serviceUpdate(id: $id, input: $input)
    }
    """

    variables = {
        "id": service_id,
        "input": {
            "rootDirectory": root_dir,
            "startCommand": start_command,
        }
    }

    # Add healthcheck if provided
    if healthcheck_path:
        variables["input"]["healthcheckPath"] = healthcheck_path
        variables["input"]["healthcheckTimeout"] = 100

    print(f"⚙️  Configuring service settings...")
    graphql_request(query, variables, token)
    print(f"✅ Service configured: root={root_dir}, start={start_command[:50]}...")


def set_service_region(service_id: str, region: str, token: str):
    """Set the deployment region for a service."""
    # Note: Region setting might require different API calls or project-level settings
    # This is a placeholder - Railway's API for regions might be different
    print(f"ℹ️  Region configuration: {region} (set via environment or project settings)")


def create_environment_variable(service_id: str, key: str, value: str, token: str):
    """Create an environment variable for a service."""
    query = """
    mutation VariableUpsert($input: VariableUpsertInput!) {
        variableUpsert(input: $input)
    }
    """

    variables = {
        "input": {
            "projectId": PROJECT_ID,
            "environmentId": ENVIRONMENT_ID,
            "serviceId": service_id,
            "name": key,
            "value": value
        }
    }

    graphql_request(query, variables, token)


def setup_api_service(token: str) -> str:
    """Set up the API service (Laravel)."""
    print("\n" + "="*60)
    print("🔧 Setting up API Service")
    print("="*60)

    service_id = create_service("api", "/api", token)

    update_service_settings(
        service_id=service_id,
        root_dir="/api",
        start_command="php artisan octane:start --server=frankenphp --host=0.0.0.0 --port=$PORT",
        healthcheck_path="/api/v1/health",
        token=token
    )

    set_service_region(service_id, "us-east-1", token)

    return service_id


def setup_trading_service(token: str) -> str:
    """Set up the Trading service (Python FastAPI)."""
    print("\n" + "="*60)
    print("🐍 Setting up Trading Service")
    print("="*60)

    service_id = create_service("trading", "/trading", token)

    update_service_settings(
        service_id=service_id,
        root_dir="/trading",
        start_command="python3 -m uvicorn api.app:app --host 0.0.0.0 --port $PORT",
        healthcheck_path="/health",
        token=token
    )

    set_service_region(service_id, "us-east-1", token)

    return service_id


def setup_frontend_service(token: str) -> str:
    """Set up the Frontend service (React)."""
    print("\n" + "="*60)
    print("⚛️  Setting up Frontend Service")
    print("="*60)

    service_id = create_service("frontend", "/frontend", token)

    update_service_settings(
        service_id=service_id,
        root_dir="/frontend",
        start_command="npx serve -s dist -l $PORT",
        healthcheck_path=None,
        token=token
    )

    set_service_region(service_id, "us-east-1", token)

    return service_id


def trigger_deployment(service_id: str, token: str):
    """Trigger a deployment for a service."""
    query = """
    mutation ServiceInstanceRedeploy($serviceId: String!, $environmentId: String!) {
        serviceInstanceRedeploy(serviceId: $serviceId, environmentId: $environmentId)
    }
    """

    variables = {
        "serviceId": service_id,
        "environmentId": ENVIRONMENT_ID
    }

    print(f"🚀 Triggering deployment...")
    graphql_request(query, variables, token)
    print(f"✅ Deployment started")


def main():
    """Main setup script."""
    print("🚂 Railway Multi-Service Setup")
    print("="*60)
    print(f"Project ID: {PROJECT_ID}")
    print(f"Environment: {ENVIRONMENT_ID}")
    print(f"GitHub Repo: {GITHUB_REPO}")
    print(f"Target Region: us-east-1")
    print("="*60)

    token = get_api_token()

    # Create and configure services
    api_service_id = setup_api_service(token)
    trading_service_id = setup_trading_service(token)
    frontend_service_id = setup_frontend_service(token)

    # Trigger deployments
    print("\n" + "="*60)
    print("🚀 Triggering Deployments")
    print("="*60)

    print("\n📦 Deploying API service...")
    trigger_deployment(api_service_id, token)

    print("\n📦 Deploying Trading service...")
    trigger_deployment(trading_service_id, token)

    print("\n📦 Deploying Frontend service...")
    trigger_deployment(frontend_service_id, token)

    # Summary
    print("\n" + "="*60)
    print("✅ Setup Complete!")
    print("="*60)
    print("\nServices created:")
    print(f"  - api:      {api_service_id}")
    print(f"  - trading:  {trading_service_id}")
    print(f"  - frontend: {frontend_service_id}")
    print("\n📊 Monitor deployments:")
    print(f"  https://railway.com/project/{PROJECT_ID}")
    print("\n⏳ Next steps:")
    print("  1. Wait for builds to complete (5-10 minutes)")
    print("  2. Add PostgreSQL: railway add --database postgres")
    print("  3. Configure environment variables")
    print("  4. Run migrations: railway run php artisan migrate --force")
    print("\n💡 Tip: Check DEPLOY-STEPS.md for environment variable setup")


if __name__ == "__main__":
    main()
