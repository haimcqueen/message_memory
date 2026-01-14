
import pytest
from unittest.mock import patch, MagicMock
from workers.jobs import process_whatsapp_message, URL_REGEX, EXCLUDED_DOMAINS
import re

# Mock Settings
@pytest.fixture
def mock_settings():
    with patch("workers.jobs.settings") as mock:
        mock.max_file_size_mb = 10
        mock.supadata_api_key = "test_key"
        yield mock

# Mock Supadata
@pytest.fixture
def mock_supadata():
    with patch("workers.jobs.supadata_client") as mock:
        yield mock

# Mock DB functions
@pytest.fixture
def mock_db_functions():
    with patch("workers.jobs.get_subscription_status_by_phone") as mock_sub, \
         patch("workers.jobs.get_user_id_by_phone") as mock_user, \
         patch("workers.jobs.insert_message") as mock_insert, \
         patch("workers.jobs.send_presence") as mock_presence, \
         patch("workers.database.update_message_content") as mock_update, \
         patch("workers.jobs.send_whatsapp_message") as mock_whatsapp:
        
        mock_sub.return_value = "active"
        mock_user.return_value = "user-123"
        yield {
            "sub": mock_sub,
            "user": mock_user,
            "insert": mock_insert,
            "update": mock_update,
            "presence": mock_presence,
            "whatsapp": mock_whatsapp
        }

def test_url_regex():
    """Test generic URL regex."""
    assert re.search(URL_REGEX, "https://example.com")
    assert re.search(URL_REGEX, "www.example.com/path")
    assert re.search(URL_REGEX, "Check this www.site.com out")

def test_website_crawler_success(mock_db_functions, mock_supadata, mock_settings):
    """Test successful website crawling and URL normalization."""
    # Mock successful scrape
    mock_scrape = MagicMock()
    mock_scrape.content = "Scraped content"
    mock_supadata.web.scrape.return_value = mock_scrape
    
    message_data = {
        "id": "msg-web-1",
        "type": "text",
        "chat_id": "123456@s.whatsapp.net",
        "from_me": False,
        "timestamp": 1234567890,
        "text": {"body": "Check www.example.com out"},
        "from": "123456"
    }

    process_whatsapp_message(message_data)

    # Verify normalization: example.com -> https://www.example.com
    mock_supadata.web.scrape.assert_called_with(url="https://www.example.com")
    
    # Verify DB insertion includes extracted content
    args, _ = mock_db_functions["insert"].call_args
    assert args[0]["extracted_media_content"] is None

    # Verify usage of update_message_content
    assert mock_db_functions["update"].called
    # args: id, content, media_url, extracted_media_content, flags
    update_args = mock_db_functions["update"].call_args[0]
    assert update_args[3] == "Scraped content"

def test_website_crawler_normalization_complex(mock_db_functions, mock_supadata, mock_settings):
    """Test URL normalization with existing protocol/www."""
    mock_scrape = MagicMock()
    mock_scrape.content = "Content"
    mock_supadata.web.scrape.return_value = mock_scrape
    
    urls = [
        ("http://test.com", "https://www.test.com"),
        ("https://www.test.org", "https://www.test.org"),
        ("www.test.net", "https://www.test.net")
    ]
    
    for input_url, expected_url in urls:
        message_data = {
            "id": "msg-norm",
            "type": "text",
            "chat_id": "123@s.whatsapp.net",
            "from_me": False,
            "timestamp": 123456,
            "text": {"body": input_url},
            "from": "123456"
        }
        process_whatsapp_message(message_data)
        mock_supadata.web.scrape.assert_called_with(url=expected_url)

def test_website_crawler_exclusions(mock_db_functions, mock_supadata, mock_settings):
    """Test that excluded domains are skipped."""
    excluded = ["https://twitter.com/user", "x.com/post", "linkedin.com/in/user", "tiktok.com/@u/video/1"]
    
    for url in excluded:
        message_data = {
            "id": "msg-exclude",
            "type": "text",
            "chat_id": "123@s.whatsapp.net",
            "from_me": False,
            "timestamp": 123456,
            "text": {"body": url},
            "from": "123456"
        }
        process_whatsapp_message(message_data)
        
        # Verify scrape was NOT called
        mock_supadata.web.scrape.assert_not_called()
        mock_supadata.web.scrape.reset_mock()

def test_website_crawler_failure(mock_db_functions, mock_supadata, mock_settings):
    """Test failure message when scraping fails."""
    mock_supadata.web.scrape.side_effect = Exception("Scrape failed")
    
    message_data = {
        "id": "msg-fail",
        "type": "text",
        "chat_id": "123456@s.whatsapp.net",
        "from_me": False,
        "timestamp": 1234567890,
        "text": {"body": "https://broken-site.com"},
        "from": "123456"
    }

    process_whatsapp_message(message_data)

    # Verify generic failure message sent
    mock_db_functions["whatsapp"].assert_any_call("123456@s.whatsapp.net", "I couldn't read that website.")
    
    # Verify DB insertion (extracted_content should be None)
    args, _ = mock_db_functions["insert"].call_args
    assert args[0]["extracted_media_content"] is None

