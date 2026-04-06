#!/usr/bin/env python3
"""Query Builder enum values"""

import os
import json
import requests

RAILWAY_API_URL = "https://backboard.railway.app/graphql/v2"

def get_token():
    with open(os.path.expanduser("~/.railway/config.json")) as f:
        config = json.load(f)
    return config["user"]["token"]

def query_enum():
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    query = """
    {
        __type(name: "Builder") {
            name
            enumValues {
                name
                description
            }
        }
    }
    """

    response = requests.post(RAILWAY_API_URL, json={"query": query}, headers=headers)
    data = response.json()

    if "errors" in data:
        print("Errors:", json.dumps(data["errors"], indent=2))
    else:
        print("Builder enum values:")
        for value in data["data"]["__type"]["enumValues"]:
            desc = value.get("description", "")
            print(f"  - {value['name']}: {desc}")

if __name__ == "__main__":
    query_enum()
