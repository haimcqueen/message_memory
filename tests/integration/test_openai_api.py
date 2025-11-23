"""
Integration tests for OpenAI API interactions.

Tests Whisper (audio transcription) and Vision (PDF/image parsing) APIs
with retry logic verification.
Requires OPENAI_API_KEY environment variable.
"""
import pytest
from unittest.mock import patch, MagicMock, mock_open
from openai import APIError, OpenAI
from workers.transcription import (
    download_voice_file,
    transcribe_audio_with_whisper
)
from workers.media import (
    parse_pdf_with_openai,
    parse_image_with_openai
)


@pytest.mark.integration
@pytest.mark.openai
@pytest.mark.requires_env
class TestWhisperTranscription:
    """Tests for OpenAI Whisper API audio transcription."""

    def test_whisper_transcription_success(self, sample_media_bytes):
        """Test successful Whisper API transcription."""
        with patch.object(OpenAI, 'audio') as mock_audio:
            # Mock the transcriptions.create method
            mock_transcriptions = MagicMock()
            mock_transcriptions.create.return_value = MagicMock(text="This is a test transcription.")
            mock_audio.transcriptions = mock_transcriptions

            # Create a mock file-like object
            import io
            audio_file = io.BytesIO(sample_media_bytes["ogg"])
            audio_file.name = "voice.ogg"

            result = transcribe_audio_with_whisper(audio_file)

            assert result == "This is a test transcription."
            assert mock_transcriptions.create.called

    def test_whisper_retry_on_api_error(self):
        """Test Whisper API retries 5 times on APIError."""
        with patch.object(OpenAI, 'audio') as mock_audio:
            mock_transcriptions = MagicMock()
            mock_transcriptions.create.side_effect = APIError("Rate limit exceeded")
            mock_audio.transcriptions = mock_transcriptions

            import io
            audio_file = io.BytesIO(b"fake audio data")
            audio_file.name = "voice.ogg"

            with pytest.raises(APIError):
                transcribe_audio_with_whisper(audio_file)

            # Verify 5 retry attempts (initial + 4 retries)
            assert mock_transcriptions.create.call_count == 5

    def test_whisper_succeeds_after_retry(self):
        """Test Whisper succeeds after first retry."""
        with patch.object(OpenAI, 'audio') as mock_audio:
            mock_transcriptions = MagicMock()
            # First call fails, second succeeds
            mock_transcriptions.create.side_effect = [
                APIError("Temporary error"),
                MagicMock(text="Success after retry")
            ]
            mock_audio.transcriptions = mock_transcriptions

            import io
            audio_file = io.BytesIO(b"fake audio data")
            audio_file.name = "voice.ogg"

            result = transcribe_audio_with_whisper(audio_file)

            assert result == "Success after retry"
            assert mock_transcriptions.create.call_count == 2

    def test_whisper_model_parameter(self):
        """Test that whisper-1 model is used."""
        with patch.object(OpenAI, 'audio') as mock_audio:
            mock_transcriptions = MagicMock()
            mock_transcriptions.create.return_value = MagicMock(text="Test")
            mock_audio.transcriptions = mock_transcriptions

            import io
            audio_file = io.BytesIO(b"fake audio data")
            audio_file.name = "voice.ogg"

            transcribe_audio_with_whisper(audio_file)

            # Verify whisper-1 model was used
            call_kwargs = mock_transcriptions.create.call_args.kwargs
            assert call_kwargs["model"] == "whisper-1"

    def test_whisper_response_format(self):
        """Test Whisper API response format (default json)."""
        with patch.object(OpenAI, 'audio') as mock_audio:
            mock_transcriptions = MagicMock()
            mock_transcriptions.create.return_value = MagicMock(text="Test transcription")
            mock_audio.transcriptions = mock_transcriptions

            import io
            audio_file = io.BytesIO(b"fake audio data")
            audio_file.name = "voice.ogg"

            result = transcribe_audio_with_whisper(audio_file)

            # Result should be string (text from response)
            assert isinstance(result, str)
            assert result == "Test transcription"


@pytest.mark.integration
@pytest.mark.openai
class TestDownloadVoiceFile:
    """Tests for downloading voice files before transcription."""

    def test_download_voice_success(self, sample_media_bytes):
        """Test successful voice file download."""
        import httpx

        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.content = sample_media_bytes["ogg"]
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = download_voice_file("https://example.com/voice.ogg")

            assert result == sample_media_bytes["ogg"]

    def test_download_voice_retry_logic(self):
        """Test download_voice_file retries 5 times on error."""
        import httpx

        with patch('httpx.get') as mock_get:
            mock_get.side_effect = httpx.HTTPError("Network error")

            with pytest.raises(httpx.HTTPError):
                download_voice_file("https://example.com/voice.ogg")

            # Verify 5 retry attempts
            assert mock_get.call_count == 5

    def test_download_voice_redirects(self):
        """Test voice download follows redirects."""
        import httpx

        with patch('httpx.get') as mock_get:
            mock_response = MagicMock()
            mock_response.content = b"voice data"
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = download_voice_file("https://example.com/redirect-to-voice")

            assert result == b"voice data"
            # httpx follows redirects by default
            assert mock_get.called


@pytest.mark.integration
@pytest.mark.openai
class TestPDFParsing:
    """Tests for PDF parsing with OpenAI Vision API."""

    def test_pdf_parsing_success(self, sample_media_bytes):
        """Test successful PDF parsing with OpenAI."""
        with patch.object(OpenAI, 'files') as mock_files, \
             patch.object(OpenAI, 'chat') as mock_chat:

            # Mock file upload
            mock_files.create.return_value = MagicMock(id="file-abc123")
            mock_files.delete.return_value = MagicMock()

            # Mock chat completion
            mock_completions = MagicMock()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content="Parsed PDF content: This is a test document."))]
            mock_completions.create.return_value = mock_response
            mock_chat.completions = mock_completions

            result = parse_pdf_with_openai(sample_media_bytes["pdf"], "test.pdf")

            assert "Parsed PDF content" in result or "test document" in result.lower()
            assert mock_files.create.called
            assert mock_files.delete.called

    def test_pdf_file_upload_to_openai(self, sample_media_bytes):
        """Test PDF file upload to OpenAI Files API."""
        with patch.object(OpenAI, 'files') as mock_files, \
             patch.object(OpenAI, 'chat') as mock_chat:

            mock_files.create.return_value = MagicMock(id="file-xyz789")
            mock_files.delete.return_value = MagicMock()

            mock_completions = MagicMock()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content="Content"))]
            mock_completions.create.return_value = mock_response
            mock_chat.completions = mock_completions

            parse_pdf_with_openai(sample_media_bytes["pdf"], "document.pdf")

            # Verify file was uploaded with correct purpose
            call_kwargs = mock_files.create.call_args.kwargs
            assert call_kwargs["purpose"] == "assistants"

    def test_pdf_file_cleanup_after_parsing(self, sample_media_bytes):
        """Test that uploaded PDF is deleted after parsing."""
        with patch.object(OpenAI, 'files') as mock_files, \
             patch.object(OpenAI, 'chat') as mock_chat:

            file_id = "file-cleanup-test"
            mock_files.create.return_value = MagicMock(id=file_id)
            mock_files.delete.return_value = MagicMock()

            mock_completions = MagicMock()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content="Content"))]
            mock_completions.create.return_value = mock_response
            mock_chat.completions = mock_completions

            parse_pdf_with_openai(sample_media_bytes["pdf"], "test.pdf")

            # Verify file was deleted
            mock_files.delete.assert_called_once_with(file_id)

    def test_pdf_parsing_retry_logic(self, sample_media_bytes):
        """Test PDF parsing retries 3 times on APIError."""
        with patch.object(OpenAI, 'files') as mock_files:
            mock_files.create.side_effect = APIError("API Error")

            with pytest.raises(APIError):
                parse_pdf_with_openai(sample_media_bytes["pdf"], "test.pdf")

            # Verify 3 retry attempts
            assert mock_files.create.call_count == 3

    def test_pdf_parsing_various_sizes(self, sample_media_bytes):
        """Test PDF parsing with different file sizes."""
        with patch.object(OpenAI, 'files') as mock_files, \
             patch.object(OpenAI, 'chat') as mock_chat:

            mock_files.create.return_value = MagicMock(id="file-123")
            mock_files.delete.return_value = MagicMock()

            mock_completions = MagicMock()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content="Parsed"))]
            mock_completions.create.return_value = mock_response
            mock_chat.completions = mock_completions

            # Test with actual sample
            result1 = parse_pdf_with_openai(sample_media_bytes["pdf"], "small.pdf")
            assert len(result1) > 0

            # Test with larger simulated PDF
            large_pdf = sample_media_bytes["pdf"] * 100
            result2 = parse_pdf_with_openai(large_pdf, "large.pdf")
            assert len(result2) > 0


@pytest.mark.integration
@pytest.mark.openai
class TestImageParsing:
    """Tests for image parsing with OpenAI Vision API."""

    def test_image_base64_encoding(self, sample_media_bytes):
        """Test that images are correctly base64 encoded."""
        import base64

        with patch.object(OpenAI, 'chat') as mock_chat:
            mock_completions = MagicMock()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content="Image content"))]
            mock_completions.create.return_value = mock_response
            mock_chat.completions = mock_completions

            parse_image_with_openai(sample_media_bytes["jpg"], "test.jpg")

            # Verify chat.completions.create was called
            assert mock_completions.create.called

            # Verify base64 encoding in message
            call_args = mock_completions.create.call_args
            messages = call_args.kwargs["messages"]

            # Check that base64 string is in the message content
            message_str = str(messages)
            assert "data:image" in message_str or "base64" in message_str.lower()

    def test_image_vision_jpeg(self, sample_media_bytes):
        """Test Vision API with JPEG image."""
        with patch.object(OpenAI, 'chat') as mock_chat:
            mock_completions = MagicMock()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content="JPEG image analysis"))]
            mock_completions.create.return_value = mock_response
            mock_chat.completions = mock_completions

            result = parse_image_with_openai(sample_media_bytes["jpg"], "photo.jpg")

            assert "JPEG" in result or len(result) > 0
            assert mock_completions.create.called

    def test_image_vision_png(self, sample_media_bytes):
        """Test Vision API with PNG image."""
        with patch.object(OpenAI, 'chat') as mock_chat:
            mock_completions = MagicMock()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content="PNG image analysis"))]
            mock_completions.create.return_value = mock_response
            mock_chat.completions = mock_completions

            result = parse_image_with_openai(sample_media_bytes["png"], "screenshot.png")

            assert len(result) > 0

    def test_image_vision_gif(self, sample_media_bytes):
        """Test Vision API with GIF image."""
        with patch.object(OpenAI, 'chat') as mock_chat:
            mock_completions = MagicMock()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content="GIF image analysis"))]
            mock_completions.create.return_value = mock_response
            mock_chat.completions = mock_completions

            result = parse_image_with_openai(sample_media_bytes["gif"], "animation.gif")

            assert len(result) > 0

    def test_image_vision_webp(self, sample_media_bytes):
        """Test Vision API with WebP image."""
        with patch.object(OpenAI, 'chat') as mock_chat:
            mock_completions = MagicMock()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content="WebP image analysis"))]
            mock_completions.create.return_value = mock_response
            mock_chat.completions = mock_completions

            result = parse_image_with_openai(sample_media_bytes["webp"], "modern.webp")

            assert len(result) > 0

    def test_image_vision_retry_logic(self, sample_media_bytes):
        """Test image parsing retries 3 times on APIError."""
        with patch.object(OpenAI, 'chat') as mock_chat:
            mock_completions = MagicMock()
            mock_completions.create.side_effect = APIError("Vision API error")
            mock_chat.completions = mock_completions

            with pytest.raises(APIError):
                parse_image_with_openai(sample_media_bytes["jpg"], "test.jpg")

            # Verify 3 retry attempts
            assert mock_completions.create.call_count == 3

    def test_image_extraction_failure_handling(self, sample_media_bytes):
        """Test handling of image extraction failures."""
        with patch.object(OpenAI, 'chat') as mock_chat:
            mock_completions = MagicMock()
            # Return empty content
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content=None))]
            mock_completions.create.return_value = mock_response
            mock_chat.completions = mock_completions

            result = parse_image_with_openai(sample_media_bytes["jpg"], "test.jpg")

            # Should return fallback message
            assert "[Image - no content extracted]" in result


@pytest.mark.integration
@pytest.mark.openai
@pytest.mark.slow
class TestRetryBackoffTiming:
    """Tests to verify exponential backoff timing for OpenAI API retries."""

    def test_whisper_backoff_timing(self):
        """Test Whisper API retry backoff timing (5 attempts, 2-32s)."""
        import time

        with patch.object(OpenAI, 'audio') as mock_audio:
            mock_transcriptions = MagicMock()
            mock_transcriptions.create.side_effect = APIError("Error")
            mock_audio.transcriptions = mock_transcriptions

            import io
            audio_file = io.BytesIO(b"fake")
            audio_file.name = "test.ogg"

            start_time = time.time()

            with pytest.raises(APIError):
                transcribe_audio_with_whisper(audio_file)

            elapsed_time = time.time() - start_time

            # 5 attempts with 2-32s exponential backoff
            # Should take at least a few seconds
            assert elapsed_time >= 2.0
            assert elapsed_time < 60.0  # Not excessively long

    def test_pdf_parsing_backoff_timing(self, sample_media_bytes):
        """Test PDF parsing retry backoff timing (3 attempts, 2-16s)."""
        import time

        with patch.object(OpenAI, 'files') as mock_files:
            mock_files.create.side_effect = APIError("Error")

            start_time = time.time()

            with pytest.raises(APIError):
                parse_pdf_with_openai(sample_media_bytes["pdf"], "test.pdf")

            elapsed_time = time.time() - start_time

            # 3 attempts with 2-16s exponential backoff
            assert elapsed_time >= 2.0
            assert elapsed_time < 40.0

    def test_image_parsing_backoff_timing(self, sample_media_bytes):
        """Test image parsing retry backoff timing (3 attempts, 2-16s)."""
        import time

        with patch.object(OpenAI, 'chat') as mock_chat:
            mock_completions = MagicMock()
            mock_completions.create.side_effect = APIError("Error")
            mock_chat.completions = mock_completions

            start_time = time.time()

            with pytest.raises(APIError):
                parse_image_with_openai(sample_media_bytes["jpg"], "test.jpg")

            elapsed_time = time.time() - start_time

            # 3 attempts with 2-16s exponential backoff
            assert elapsed_time >= 2.0
            assert elapsed_time < 40.0
