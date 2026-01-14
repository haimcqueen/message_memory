
import pytest
import re
from workers.jobs import URL_REGEX

def test_url_detection_regex():
    """Verify strict URL regex behavior."""
    
    # 1. Ignored cases (False Positives in old regex)
    assert not re.search(URL_REGEX, "kling 2.0"), "Should not match '2.0' (space)"
    assert not re.search(URL_REGEX, "version 2.0 is out"), "Should not match version numbers"
    assert not re.search(URL_REGEX, "google.com"), "Should ignore domains without http/www prefix"
    assert not re.search(URL_REGEX, "docs.python.org"), "Should ignore subdomains without http/www"
    assert not re.search(URL_REGEX, "file.txt"), "Should ignore filenames"

    # 2. MATCHED cases (Valid)
    # HTTPS
    match = re.search(URL_REGEX, "Check out https://kling.ai now")
    assert match
    assert match.group(0) == "https://kling.ai"

    # HTTP
    match = re.search(URL_REGEX, "http://insecure.com")
    assert match
    assert match.group(0) == "http://insecure.com"

    # WWW
    match = re.search(URL_REGEX, "Go to www.google.com please")
    assert match
    assert match.group(0) == "www.google.com"
    
    # WWW with https
    match = re.search(URL_REGEX, "https://www.google.com")
    assert match
    assert match.group(0) == "https://www.google.com"

    # Complex URL
    url = "https://news.ycombinator.com/item?id=123"
    match = re.search(URL_REGEX, f"Link: {url}")
    assert match
    assert match.group(0) == url
