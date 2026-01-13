
import pytest
from unittest.mock import patch, MagicMock
from workers.jobs import process_whatsapp_message
import json

# Mock Settings
@pytest.fixture
def mock_settings():
    with patch("workers.jobs.settings") as mock:
        mock.supadata_api_key = "test_key"
        mock.openai_api_key = "test_openai_key"
        yield mock

# Mock DB functions
@pytest.fixture
def mock_db_functions():
    with patch("workers.jobs.get_subscription_status_by_phone") as mock_sub, \
         patch("workers.jobs.get_user_id_by_phone") as mock_user, \
         patch("workers.jobs.insert_message") as mock_insert, \
         patch("workers.jobs.get_publyc_persona") as mock_get_persona, \
         patch("workers.jobs.update_publyc_persona_field") as mock_update_persona, \
         patch("workers.jobs.send_presence") as mock_presence, \
         patch("workers.jobs.send_whatsapp_message") as mock_whatsapp:
        
        mock_sub.return_value = "active"
        mock_user.return_value = "user-123"
        yield {
            "sub": mock_sub,
            "user": mock_user,
            "insert": mock_insert,
            "get_persona": mock_get_persona,
            "update_persona": mock_update_persona,
            "presence": mock_presence
        }

# Mock OpenAI via utils.llm
@pytest.fixture
def mock_llm():
    with patch("workers.jobs.classify_message") as mock_classify, \
         patch("workers.jobs.process_persona_update") as mock_update_logic:
        yield {
            "classify": mock_classify,
            "process": mock_update_logic
        }

def test_persona_classification_only(mock_db_functions, mock_llm, mock_settings):
    """Test message is classified but not an update (e.g. fact)."""
    mock_llm["classify"].return_value = "fact"

    message_data = {
        "id": "msg-fact",
        "type": "text",
        "chat_id": "123@s.whatsapp.net",
        "from_me": False,  # USER origin
        "timestamp": 123456,
        "text": {"body": "I visited Paris last year."},
        "from": "123456"
    }

    process_whatsapp_message(message_data)

    # Verify classification called
    mock_llm["classify"].assert_called_with("I visited Paris last year.")
    
    # Verify DB insertion has flags
    args, _ = mock_db_functions["insert"].call_args
    assert args[0]["flags"] == {"classification": "fact"}
    
    # Verify NO persona fetching/update
    mock_db_functions["get_persona"].assert_not_called()
    mock_db_functions["update_persona"].assert_not_called()

def test_persona_update_flow(mock_db_functions, mock_llm, mock_settings):
    """Test full persona update flow."""
    mock_llm["classify"].return_value = "persona"
    mock_db_functions["get_persona"].return_value = {"user_id": "user-123", "business_goals": "old goal"}
    mock_llm["process"].return_value = {"field": "business_goals", "value": "new goal"}

    message_data = {
        "id": "msg-persona",
        "type": "text",
        "chat_id": "123@s.whatsapp.net",
        "from_me": False,
        "timestamp": 123456,
        "text": {"body": "My goal is to reach 1M users."},
        "from": "123456"
    }

    process_whatsapp_message(message_data)

    # Verify flow
    mock_llm["classify"].assert_called()
    mock_db_functions["get_persona"].assert_called_with("user-123")
    mock_llm["process"].assert_called()
    
    # Verify DB update called
    mock_db_functions["update_persona"].assert_called_with("user-123", "business_goals", "new goal")
    
    # Verify DB insertion includes update info
    args, _ = mock_db_functions["insert"].call_args
    flags = args[0]["flags"]
    assert flags["classification"] == "persona"
    assert flags["persona_update"] == {"field": "business_goals", "value": "new goal"}

def test_skip_classification_for_agent(mock_db_functions, mock_llm, mock_settings):
    """Test agent messages are skipped for classification."""
    
    message_data = {
        "id": "msg-agent",
        "type": "text",
        "chat_id": "123@s.whatsapp.net",
        "from_me": True,  # AGENT origin
        "timestamp": 123456,
        "text": {"body": "Hello user"},
        "from": "123456"
    }

    process_whatsapp_message(message_data)

    # Verify classification NOT called
    mock_llm["classify"].assert_not_called()
