#!/usr/bin/env python3
"""Query available Service mutations"""

import os
import json
import requests

RAILWAY_API_URL = "https://backboard.railway.app/graphql/v2"

def get_token():
    with open(os.path.expanduser("~/.railway/config.json")) as f:
        config = json.load(f)
    return config["user"]["token"]

def query_mutations():
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    query = """
    {
        __schema {
            mutationType {
                fields {
                    name
                    description
                    args {
                        name
                        type {
                            name
                            kind
                        }
                    }
                }
            }
        }
    }
    """

    response = requests.post(RAILWAY_API_URL, json={"query": query}, headers=headers)
    data = response.json()

    if "errors" in data:
        print("Errors:", json.dumps(data["errors"], indent=2))
    else:
        mutations = data["data"]["__schema"]["mutationType"]["fields"]
        service_mutations = [m for m in mutations if "service" in m["name"].lower()]

        print("Service-related mutations:")
        for mutation in service_mutations:
            args_str = ", ".join([f"{a['name']}" for a in mutation.get("args", [])])
            desc = mutation.get("description", "")[:60]
            print(f"  - {mutation['name']}({args_str})")
            if desc:
                print(f"      {desc}")

if __name__ == "__main__":
    query_mutations()
