
import unittest
from unittest.mock import MagicMock, patch
import json
from utils.llm import process_persona_update

class TestPersonaSafeguards(unittest.TestCase):
    def setUp(self):
        self.mock_persona = {
            "voice_style": {
                "inspiration": "Tests",
                "tone": "Safe"
            },
            "your_story": "Be robust"
        }

    @patch("utils.llm.openai_client")
    def test_blocks_flattening_of_dict_field(self, mock_openai):
        # Simulate LLM returning a string for a dict field
        flattened_response = {
            "field": "voice_style",
            "value": "This is a flattened string replacing the object."
        }
        
        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = json.dumps(flattened_response)
        mock_openai.chat.completions.create.return_value = mock_completion

        # Attempt update
        result = process_persona_update("Update my voice", self.mock_persona)

        # Should be None because it was blocked
        self.assertIsNone(result)

    @patch("utils.llm.openai_client")
    def test_allows_dict_update_for_dict_field(self, mock_openai):
        # Simulate LLM returning a valid dict for a dict field
        valid_response = {
            "field": "voice_style",
            "value": {
                "inspiration": "New Tests",
                "tone": "Safer"
            }
        }
        
        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = json.dumps(valid_response)
        mock_openai.chat.completions.create.return_value = mock_completion

        # Attempt update
        result = process_persona_update("Update my voice", self.mock_persona)

        # Should match
        self.assertIsNotNone(result)
        self.assertEqual(result["field"], "voice_style")
        self.assertIsInstance(result["value"], dict)
        self.assertEqual(result["value"]["tone"], "Safer")

    @patch("utils.llm.openai_client")
    def test_allows_string_update_for_string_field(self, mock_openai):
        # Simulate LLM returning a string for a string field
        valid_response = {
            "field": "your_story",
            "value": "New goal is to be super robust"
        }
        
        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = json.dumps(valid_response)
        mock_openai.chat.completions.create.return_value = mock_completion

        # Attempt update
        result = process_persona_update("Update my goals", self.mock_persona)

        # Should match
        self.assertIsNotNone(result)
        self.assertEqual(result["field"], "your_story")
        self.assertIsInstance(result["value"], str)

if __name__ == "__main__":
    unittest.main()
