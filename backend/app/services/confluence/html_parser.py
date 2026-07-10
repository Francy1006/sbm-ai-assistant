from bs4 import BeautifulSoup
import html


def clean_html_to_text(raw_html: str) -> str:
    decoded_html = html.unescape(raw_html)

    soup = BeautifulSoup(decoded_html, "html.parser")

    text = soup.get_text(separator="\n")

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    return "\n".join(lines)