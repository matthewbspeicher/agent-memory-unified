#!/usr/bin/env python3
"""Query Railway GraphQL schema"""

import os
import sys
import requests
import json

RAILWAY_API_URL = "https://backboard.railway.app/graphql/v2"

def get_token():
    with open(os.path.expanduser("~/.railway/config.json")) as f:
        config = json.load(f)
    return config["user"]["token"]

def query_schema():
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # Introspection query for ServiceUpdateInput type
    query = """
    {
        __type(name: "ServiceInstanceUpdateInput") {
            name
            inputFields {
                name
                type {
                    name
                    kind
                    ofType {
                        name
                        kind
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
        print("ServiceInstanceUpdateInput fields:")
        for field in data["data"]["__type"]["inputFields"]:
            type_info = field["type"]
            if type_info.get("ofType"):
                type_name = type_info["ofType"]["name"]
            else:
                type_name = type_info["name"]
            print(f"  - {field['name']}: {type_name}")

if __name__ == "__main__":
    query_schema()
