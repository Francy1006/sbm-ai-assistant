import os
import requests
from requests.auth import HTTPBasicAuth

CONFLUENCE_BASE_URL = os.getenv("CONFLUENCE_BASE_URL")
CONFLUENCE_EMAIL = os.getenv("CONFLUENCE_EMAIL")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
CONFLUENCE_SPACE_KEY = os.getenv("CONFLUENCE_SPACE_KEY")


def test_confluence_connection():
    url = f"{CONFLUENCE_BASE_URL}/rest/api/space/{CONFLUENCE_SPACE_KEY}"

    response = requests.get(
        url,
        auth=HTTPBasicAuth(CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN),
        headers={"Accept": "application/json"},
        timeout=15
    )

    return {
        "status_code": response.status_code,
        "ok": response.ok,
        "response": response.json() if response.content else None
    }



def list_pages():
    url = f"{CONFLUENCE_BASE_URL}/rest/api/content"

    response = requests.get(
        url,
        auth=HTTPBasicAuth(CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN),
        headers={"Accept": "application/json"},
        params={
            "spaceKey": CONFLUENCE_SPACE_KEY,
            "type": "page",
            "limit": 10
        },
        timeout=15
    )

    return {
        "status_code": response.status_code,
        "ok": response.ok,
        "response": response.json() if response.content else None
    }


def get_page_content(page_id: str):
    url = f"{CONFLUENCE_BASE_URL}/rest/api/content/{page_id}"

    response = requests.get(
        url,
        auth=HTTPBasicAuth(CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN),
        headers={"Accept": "application/json"},
        params={
            "expand": "body.storage,version,space"
        },
        timeout=15
    )

    return {
        "status_code": response.status_code,
        "ok": response.ok,
        "response": response.json() if response.content else None
    }