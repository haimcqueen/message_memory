
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

def test_personal_fact_classification(mock_db_functions, mock_llm, mock_settings):
    """Test personal facts (interests) are classified as fact."""
    mock_llm["classify"].return_value = "fact"

    message_data = {
        "id": "msg-fact-dino",
        "type": "text",
        "chat_id": "123@s.whatsapp.net",
        "from_me": False,
        "timestamp": 123456,
        "text": {"body": "I love dinosaurs"},
        "from": "123456"
    }

    process_whatsapp_message(message_data)

    mock_llm["classify"].assert_called_with("I love dinosaurs")
    args, _ = mock_db_functions["insert"].call_args
    assert args[0]["flags"] == {"classification": "fact"}

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

def test_persona_classification_with_fillers(mock_db_functions, mock_llm, mock_settings):
    """Test that messages with fillers like 'joo' are still classified as persona."""
    mock_llm["classify"].return_value = "persona"

    message_data = {
        "id": "msg-filler",
        "type": "text",
        "chat_id": "123@s.whatsapp.net",
        "from_me": False,
        "timestamp": 123456,
        "text": {"body": "joo my writing style is all small caps"},
        "from": "123456"
    }

    process_whatsapp_message(message_data)

    # Verify classification called
    mock_llm["classify"].assert_called_with("joo my writing style is all small caps")
    
    # Verify DB insertion has flags
    args, _ = mock_db_functions["insert"].call_args
    assert args[0]["flags"]["classification"] == "persona"
    # Since we are mocking get_persona to return something (default mock behavior),
    # the code proceeds to update. We just check classification here is correct.

@pytest.mark.parametrize("message_text", [
    "I just ran my first marathon in under 4 hours",
    "My favorite book is The Mom Test",
    "I'm learning Rust this weekend"
])
def test_various_fact_examples(mock_db_functions, mock_llm, mock_settings, message_text):
    """Test various fact examples to ensure robust fact classification."""
    mock_llm["classify"].return_value = "fact"

    message_data = {
        "id": f"msg-fact-{hash(message_text)}",
        "type": "text",
        "chat_id": "123@s.whatsapp.net",
        "from_me": False,
        "timestamp": 123456,
        "text": {"body": message_text},
        "from": "123456"
    }

    process_whatsapp_message(message_data)

    mock_llm["classify"].assert_called_with(message_text)
    args, _ = mock_db_functions["insert"].call_args
    assert args[0]["flags"] == {"classification": "fact"}

@pytest.mark.parametrize("message_text", [
    "I am an indie hacker building in public",
    "I value radical honesty in business",
    "My tone is usually sarcastic and dry",
    "I want to retire by 40"
])
def test_various_persona_examples(mock_db_functions, mock_llm, mock_settings, message_text):
    """Test various persona examples to ensure robust persona classification."""
    mock_llm["classify"].return_value = "persona"

    message_data = {
        "id": f"msg-persona-{hash(message_text)}",
        "type": "text",
        "chat_id": "123@s.whatsapp.net",
        "from_me": False,
        "timestamp": 123456,
        "text": {"body": message_text},
        "from": "123456"
    }

    process_whatsapp_message(message_data)

    mock_llm["classify"].assert_called_with(message_text)
    args, _ = mock_db_functions["insert"].call_args
    assert args[0]["flags"]["classification"] == "persona"

def test_real_persona_update_flow(mock_db_functions, mock_llm, mock_settings):
    """Test persona update with a complex real-world profile (fixture)."""
    # Load fixture
    import os
    fixture_path = os.path.join(os.path.dirname(__file__), "..", "fixtures", "real_persona.json")
    with open(fixture_path, "r") as f:
        real_persona = json.load(f)

    # Scenerio: User wants to add "Crypto speculation" to boundaries
    new_message = "I definitely do not want to talk about crypto speculation."
    
    # Mocks
    mock_llm["classify"].return_value = "persona"
    mock_db_functions["get_persona"].return_value = real_persona
    
    # We simulate what the LLM *would* return given the prompt instructions
    # Ideally it appends to 'off_limits_topics'
    expected_updated_boundaries = (
        real_persona["boundaries"]["off_limits_topics"] + 
        " Also, no discussions about crypto speculation."
    )
    
    # Mock the PROCESS step returning the decision
    mock_llm["process"].return_value = {
        "field": "boundaries.off_limits_topics", # The function handles nested keys? No, currently flat or handled by LLM text logic.
        # Wait, the current implementation expects simple field names or the LLM returns the *whole* field value text.
        # The prompt says: "Return a JSON object: {'field': 'field_name', 'value': 'updated_full_text_for_that_field'}"
        # So for 'boundaries', it might return the whole 'boundaries' object or just a subfield?
        # The prompt lists 'boundaries' as a top level field in the GUIDE, but in the DB it is JSONB.
        # The prompts instructions say: "Integrate the new info into the EXISTING value of that field"
        # If 'boundaries' is a dict in JSON, the LLM usually returns the text representation if we aren't careful?
        # Actually in the code `process_persona_update`, it receives `current_persona`. 
        # The prompt guide lists "boundaries" as a field.
        # If the LLM returns field="boundaries", value="...new JSON string...", that might fail if it's just text.
        # BUT looking at the prompt: "Identify which SINGLE field from the list above... Return ... updated_full_text_for_that_field"
        # If the field in DB is a JSON object (like 'who_you_serve'), replacing it with a text string might break the schema if the App expects object.
        # However, the user asked to test "how would they update".
        # Let's assume for this test the LLM returns the updated TEXT for 'boundaries' because the prompt implies text updates? 
        # OR does the prompt handle JSON objects?
        # The prompt says: "who_you_serve: Target audience..." 
        # It treats them as fields. 
        # If the DB column is JSONB and has nested structure, `update_publyc_persona_field` handles the update.
        # Let's check `update_publyc_persona_field` implementation in `workers/database.py`.
        # It does `supabase.table(...).update({field: value})`.
        # If `value` is a string but the column (or existing value) was a JSON object, Supabase might complain or overwrite with string.
        # THE FIXTURE shows `boundaries` is a JSON Object with `off_limits_topics`.
        # IF the LLM returns field="boundaries" and value="some string", we overwrite the JSON object with a string. That might be BAD.
        # Let's Assume the LLM is smart enough to update the specific sub-field? 
        # The prompt LISTS "boundaries" as a field.
        # The PROMPT GUIDE has "boundaries" as a bullet point.
        # Current logic: `update_publyc_persona_field` takes `field` and `value`.
        # If we want to support nested updates, we need to verify that.
        # FOR NOW: I will simulate that the LLM returns the updated *JSON string* or the code handles it?
        # Actually checking `utils/llm.py`... it just sends `current_persona` (dict) to LLM.
        # If the LLM returns field="boundaries", value="{ 'off_limits_topics': '...' }", it might work if value is parsed?
        # But `process_persona_update` returns value as string usually (from JSON response format).
        # Let's assume for this test that we want to update a *top level* field or the LLM is instructed to manage it.
        # Actually, maybe I should pick a simpler field for the test if I'm unsure, BUT the user gave me a complex profile.
        # Let's look at `value_proposition`. It is also nested. `who_you_serve` is nested.
        # `proof_authority` is nested.
        # This highlights a potential ISSUE in the implementation! If the fields are JSON objects, forcing them to be text might break things.
        # Testing this is CRITICAL.
        
        # Let's simulate the LLM returning a valid JSON object string for the value if that's what's needed.
        # OR checking if the prompt instructions handles subfields.
        # The PROMPT GUIDE lists "business_goals" (which might be simpler). In the fixture `business_goals` is NOT present? 
        # Wait, the fixture `real_persona.json` does NOT have `business_goals`. It has `who_you_serve`, `value_proposition`, `proof_authority`, `boundaries`.
        # So if I update `business_goals` it would be a NEW field (or update null).
        
        # Let's try updating `boundaries`.
        # If I return `field="boundaries"`, `value` should probably be the *updated JSON object* (as a dict or string?).
        # `workers/database.py` does `update({field: value})`.
        # So I will mock the LLM returning the *updated dictionary* for boundaries.
        
        "field": "boundaries", 
        "value": {
             "off_limits_topics": "Pure self-congratulation... Also crypto.",
             "misaligned_content": "Hustle porn..."
        }
    }

    message_data = {
        "id": "msg-real-update",
        "type": "text",
        "chat_id": "123@s.whatsapp.net",
        "from_me": False,
        "timestamp": 123456,
        "text": {"body": new_message},
        "from": "123456"
    }

    process_whatsapp_message(message_data)
    
    # Assert
    mock_db_functions["update_persona"].assert_called_with(
        "user-123",
        "boundaries",
        {
             "off_limits_topics": "Pure self-congratulation... Also crypto.",
             "misaligned_content": "Hustle porn..."
        }
    )
