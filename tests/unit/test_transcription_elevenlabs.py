"""Tests for ElevenLabs transcription worker."""
import pytest
from unittest.mock import Mock, MagicMock, patch
from types import SimpleNamespace


class TestStitchTranscript:
    """Tests for stitch_transcript function."""

    def _make_word(self, text: str, start: float, end: float = None, word_type: str = "word"):
        """Helper to create mock word objects."""
        word = SimpleNamespace()
        word.text = text
        word.start = start
        word.end = end if end else start + 0.5
        word.type = word_type
        return word

    def _make_diarized_word(self, text: str, start: float, speaker_id: str, end: float = None):
        """Helper to create mock diarized word objects."""
        word = self._make_word(text, start, end)
        word.speaker_id = speaker_id
        return word

    def _make_multichannel_response(self, agent_words: list, user_words: list):
        """Helper to create mock multichannel ElevenLabs response."""
        response = SimpleNamespace()
        response.transcripts = [
            SimpleNamespace(channel_index=0, words=agent_words),
            SimpleNamespace(channel_index=1, words=user_words),
        ]
        return response

    def _make_diarized_response(self, words: list):
        """Helper to create mock diarized ElevenLabs response."""
        response = SimpleNamespace()
        response.words = words
        return response

    def test_dual_mode_simple_conversation(self):
        """Test basic dual mode with non-overlapping speech."""
        from workers.transcription_elevenlabs import stitch_transcript

        agent_words = [
            self._make_word("Hello.", 0.0, 0.5),
            self._make_word("How", 2.0, 2.3),
            self._make_word("are", 2.3, 2.5),
            self._make_word("you?", 2.5, 3.0),
        ]
        user_words = [
            self._make_word("Hi!", 1.0, 1.5),
            self._make_word("I'm", 3.5, 3.8),
            self._make_word("good.", 3.8, 4.2),
        ]

        response = self._make_multichannel_response(agent_words, user_words)
        result = stitch_transcript(response, mode="dual")

        assert "[agent]: Hello." in result
        assert "[user]: Hi!" in result
        assert "[agent]: How are you?" in result
        assert "[user]: I'm good." in result

    def test_dual_mode_overlapping_speech_sentence_level(self):
        """Test that overlapping speech is stitched at sentence level, not word level."""
        from workers.transcription_elevenlabs import stitch_transcript

        # Simulate overlapping: agent says "Yeah, it's important." while user is talking
        agent_words = [
            self._make_word("Yeah,", 5.0, 5.3),
            self._make_word("it's", 5.3, 5.5),
            self._make_word("important.", 5.5, 6.0),
        ]
        user_words = [
            self._make_word("This", 4.8, 5.0),
            self._make_word("is", 5.0, 5.1),
            self._make_word("a", 5.1, 5.2),
            self._make_word("test.", 5.2, 5.5),
        ]

        response = self._make_multichannel_response(agent_words, user_words)
        result = stitch_transcript(response, mode="dual")

        # Should NOT have choppy word-by-word interleaving
        # Each speaker's sentence should be complete
        assert "[user]: This is a test." in result
        assert "[agent]: Yeah, it's important." in result

    def test_dual_mode_consecutive_sentences_same_speaker(self):
        """Test that consecutive sentences from same speaker are merged."""
        from workers.transcription_elevenlabs import stitch_transcript

        agent_words = [
            self._make_word("First.", 0.0, 0.5),
            self._make_word("Second.", 0.6, 1.0),
            self._make_word("Third.", 1.1, 1.5),
        ]
        user_words = []

        response = self._make_multichannel_response(agent_words, user_words)
        result = stitch_transcript(response, mode="dual")

        # All sentences should be in one turn
        assert result.count("[agent]:") == 1
        assert "First. Second. Third." in result

    def test_dual_mode_no_punctuation(self):
        """Test handling of text without sentence-ending punctuation."""
        from workers.transcription_elevenlabs import stitch_transcript

        agent_words = [
            self._make_word("This", 0.0, 0.3),
            self._make_word("has", 0.3, 0.5),
            self._make_word("no", 0.5, 0.7),
            self._make_word("punctuation", 0.7, 1.0),
        ]
        user_words = []

        response = self._make_multichannel_response(agent_words, user_words)
        result = stitch_transcript(response, mode="dual")

        # Should still produce output (as final segment)
        assert "[agent]: This has no punctuation" in result

    def test_dual_mode_empty_response(self):
        """Test handling of empty transcription."""
        from workers.transcription_elevenlabs import stitch_transcript

        response = self._make_multichannel_response([], [])
        result = stitch_transcript(response, mode="dual")

        assert result == ""

    def test_dual_mode_single_speaker_only(self):
        """Test when only one speaker has content."""
        from workers.transcription_elevenlabs import stitch_transcript

        agent_words = []
        user_words = [
            self._make_word("Only", 0.0, 0.3),
            self._make_word("user", 0.3, 0.5),
            self._make_word("speaks.", 0.5, 0.8),
        ]

        response = self._make_multichannel_response(agent_words, user_words)
        result = stitch_transcript(response, mode="dual")

        assert "[user]: Only user speaks." in result
        assert "[agent]" not in result

    def test_irl_mode_diarization(self):
        """Test IRL mode with diarization."""
        from workers.transcription_elevenlabs import stitch_transcript

        words = [
            self._make_diarized_word("Hello.", 0.0, "speaker_0"),
            self._make_diarized_word("Hi!", 1.0, "speaker_1"),
            self._make_diarized_word("How", 2.0, "speaker_0"),
            self._make_diarized_word("are", 2.2, "speaker_0"),
            self._make_diarized_word("you?", 2.4, "speaker_0"),
        ]

        response = self._make_diarized_response(words)
        result = stitch_transcript(response, mode="irl")

        assert "[agent]: Hello." in result
        assert "[user]: Hi!" in result
        assert "[agent]:" in result
        assert "How are you?" in result

    def test_format_output_double_newlines(self):
        """Test that turns are separated by double newlines."""
        from workers.transcription_elevenlabs import stitch_transcript

        agent_words = [self._make_word("Hello.", 0.0, 0.5)]
        user_words = [self._make_word("Hi.", 1.0, 1.5)]

        response = self._make_multichannel_response(agent_words, user_words)
        result = stitch_transcript(response, mode="dual")

        assert "\n\n" in result
        lines = result.split("\n\n")
        assert len(lines) == 2


class TestSaveTranscriptToDb:
    """Tests for save_transcript_to_db function."""

    def test_insert_new_transcript(self, mock_supabase):
        """Test inserting transcript when no row exists."""
        from workers.transcription_elevenlabs import save_transcript_to_db

        # Setup: no existing row
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = Mock(data=[])

        with patch("workers.transcription_elevenlabs.get_supabase", return_value=mock_supabase):
            save_transcript_to_db("user-123", "Test transcript")

        # Verify insert was called
        mock_supabase.table.return_value.insert.assert_called_once()
        call_args = mock_supabase.table.return_value.insert.call_args[0][0]
        assert call_args["user_id"] == "user-123"
        assert call_args["onboarding_call_transcript"] == "Test transcript"

    def test_append_to_existing_transcript(self, mock_supabase):
        """Test appending transcript when row exists with content."""
        from workers.transcription_elevenlabs import save_transcript_to_db

        # Setup: existing row with transcript
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = Mock(
            data=[{"onboarding_call_transcript": "Previous transcript"}]
        )

        with patch("workers.transcription_elevenlabs.get_supabase", return_value=mock_supabase):
            save_transcript_to_db("user-123", "New transcript")

        # Verify update was called with concatenated content
        mock_supabase.table.return_value.update.assert_called_once()
        call_args = mock_supabase.table.return_value.update.call_args[0][0]
        assert "Previous transcript" in call_args["onboarding_call_transcript"]
        assert "\n\n---\n\n" in call_args["onboarding_call_transcript"]
        assert "New transcript" in call_args["onboarding_call_transcript"]

    def test_insert_when_existing_row_has_null_transcript(self, mock_supabase):
        """Test that we handle existing row with null transcript."""
        from workers.transcription_elevenlabs import save_transcript_to_db

        # Setup: existing row but transcript is None
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = Mock(
            data=[{"onboarding_call_transcript": None}]
        )

        with patch("workers.transcription_elevenlabs.get_supabase", return_value=mock_supabase):
            save_transcript_to_db("user-123", "First transcript")

        # Verify update was called (row exists) but without separator
        mock_supabase.table.return_value.update.assert_called_once()
        call_args = mock_supabase.table.return_value.update.call_args[0][0]
        assert call_args["onboarding_call_transcript"] == "First transcript"
        assert "---" not in call_args["onboarding_call_transcript"]

    def test_insert_when_existing_row_has_empty_transcript(self, mock_supabase):
        """Test that we handle existing row with empty string transcript."""
        from workers.transcription_elevenlabs import save_transcript_to_db

        # Setup: existing row but transcript is empty string
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = Mock(
            data=[{"onboarding_call_transcript": ""}]
        )

        with patch("workers.transcription_elevenlabs.get_supabase", return_value=mock_supabase):
            save_transcript_to_db("user-123", "First transcript")

        # Verify update was called without separator
        mock_supabase.table.return_value.update.assert_called_once()
        call_args = mock_supabase.table.return_value.update.call_args[0][0]
        assert call_args["onboarding_call_transcript"] == "First transcript"
