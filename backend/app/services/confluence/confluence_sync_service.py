from app.services.confluence.confluence_client import list_pages


def get_confluence_pages_for_sync():
    pages = list_pages()

    return [
        {
            "page_id": page["id"],
            "title": page["title"],
        }
        for page in pages["response"]["results"]
    ]