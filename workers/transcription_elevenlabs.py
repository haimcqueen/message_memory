"""ElevenLabs transcription worker for onboarding call recordings."""
import workers.logging_config  # Initialize logging for worker processes
import logging
import subprocess
import httpx
from pathlib import Path
from typing import Dict, Any, List
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
from elevenlabs import ElevenLabs
from utils.config import settings
from utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

# Initialize ElevenLabs client
elevenlabs_client = ElevenLabs(api_key=settings.elevenlabs_api_key)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(httpx.HTTPError),
    reraise=True
)
def download_from_storage(url: str, output_path: Path) -> None:
    """
    Download file from Supabase Storage URL.

    Args:
        url: Full Supabase Storage URL
        output_path: Local path to save the file
    """
    logger.info(f"Downloading from {url} to {output_path}")

    response = httpx.get(url, timeout=120.0, follow_redirects=True)
    response.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(response.content)

    logger.info(f"Downloaded {len(response.content)} bytes to {output_path}")


def combine_stereo_opus(mic_path: Path, system_path: Path, output_path: Path) -> None:
    """
    Combine two mono audio files into stereo opus using ffmpeg CLI.

    Args:
        mic_path: Path to mic recording (will be left channel - agent)
        system_path: Path to system recording (will be right channel - user)
        output_path: Path for output stereo opus file
    """
    logger.info(f"Combining {mic_path} and {system_path} into stereo opus")

    cmd = [
        "ffmpeg",
        "-y",  # Overwrite output file if exists
        "-i", str(mic_path),
        "-i", str(system_path),
        # Use 'join' instead of 'amerge' to preserve the longest input's duration
        # amerge truncates to shortest, join pads the shorter with silence
        "-filter_complex",
        "[0:a][1:a]join=inputs=2:channel_layout=stereo:map=0.0-FL|1.0-FR[a]",
        "-map", "[a]",
        "-c:a", "libopus",
        str(output_path)
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300  # 5 minute timeout
    )

    if result.returncode != 0:
        logger.error(f"ffmpeg failed: {result.stderr}")
        raise RuntimeError(f"ffmpeg failed with code {result.returncode}: {result.stderr}")

    logger.info(f"Created stereo opus file: {output_path}")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=16),
    reraise=True
)
def transcribe_with_elevenlabs(audio_path: Path, mode: str) -> Dict[str, Any]:
    """
    Transcribe audio using ElevenLabs Speech-to-Text API.

    Args:
        audio_path: Path to audio file
        mode: "dual" for multichannel, "irl" for diarization

    Returns:
        ElevenLabs API response as dict
    """
    logger.info(f"Transcribing {audio_path} with mode={mode}")

    with open(audio_path, "rb") as audio_file:
        if mode == "dual":
            # Multichannel mode - channels already separated
            result = elevenlabs_client.speech_to_text.convert(
                file=audio_file,
                model_id="scribe_v1",
                use_multi_channel=True,
                diarize=False,
                timestamps_granularity="word"
            )
        else:
            # IRL mode - need diarization
            result = elevenlabs_client.speech_to_text.convert(
                file=audio_file,
                model_id="scribe_v1",
                diarize=True,
                num_speakers=2,
                timestamps_granularity="word"
            )

    logger.info(f"Transcription completed for {audio_path}")
    return result


def stitch_transcript(elevenlabs_response: Any, mode: str) -> str:
    """
    Convert ElevenLabs response into formatted dialog transcript.

    Uses sentence-level stitching: collects all words per speaker into complete
    sentences before allowing a speaker switch. This prevents choppy interleaving
    when speakers overlap.

    Args:
        elevenlabs_response: Response from ElevenLabs API
        mode: "dual" for multichannel, "irl" for diarization

    Returns:
        Formatted transcript string with [agent] and [user] labels
    """
    logger.info(f"Stitching transcript with mode={mode}")

    # Collect sentences per speaker (not individual words)
    # Each sentence: {"text": "...", "start": first_word_start, "end": last_word_end, "speaker": "..."}
    agent_sentences: List[Dict[str, Any]] = []
    user_sentences: List[Dict[str, Any]] = []

    if mode == "dual":
        # Multichannel response - process each channel separately
        if hasattr(elevenlabs_response, 'transcripts'):
            for transcript in elevenlabs_response.transcripts:
                channel = transcript.channel_index
                # Channel 0 = mic = agent, Channel 1 = system = user
                speaker = "agent" if channel == 0 else "user"
                target_list = agent_sentences if speaker == "agent" else user_sentences

                # Build sentences from words
                current_sentence: List[str] = []
                sentence_start: float = 0.0
                sentence_end: float = 0.0

                for word in transcript.words or []:
                    if word.type == "word":
                        if not current_sentence:
                            sentence_start = word.start
                        current_sentence.append(word.text)
                        sentence_end = getattr(word, 'end', word.start)

                        # Check if this word ends a sentence
                        if word.text and word.text[-1] in '.!?':
                            target_list.append({
                                "text": " ".join(current_sentence),
                                "start": sentence_start,
                                "end": sentence_end,
                                "speaker": speaker
                            })
                            current_sentence = []

                # Add any remaining words as a final segment
                if current_sentence:
                    target_list.append({
                        "text": " ".join(current_sentence),
                        "start": sentence_start,
                        "end": sentence_end,
                        "speaker": speaker
                    })
        else:
            # Fallback for single channel response
            logger.warning("Expected multichannel response but got single channel")
            current_sentence: List[str] = []
            sentence_start: float = 0.0
            sentence_end: float = 0.0

            for word in elevenlabs_response.words or []:
                if word.type == "word":
                    if not current_sentence:
                        sentence_start = word.start
                    current_sentence.append(word.text)
                    sentence_end = getattr(word, 'end', word.start)

                    if word.text and word.text[-1] in '.!?':
                        agent_sentences.append({
                            "text": " ".join(current_sentence),
                            "start": sentence_start,
                            "end": sentence_end,
                            "speaker": "agent"
                        })
                        current_sentence = []

            if current_sentence:
                agent_sentences.append({
                    "text": " ".join(current_sentence),
                    "start": sentence_start,
                    "end": sentence_end,
                    "speaker": "agent"
                })
    else:
        # IRL mode - diarization response, group by speaker
        agent_words: List[Dict[str, Any]] = []
        user_words: List[Dict[str, Any]] = []

        for word in elevenlabs_response.words or []:
            if word.type == "word":
                speaker_id = getattr(word, 'speaker_id', 'speaker_0')
                target = agent_words if speaker_id == "speaker_0" else user_words
                target.append({
                    "text": word.text,
                    "start": word.start,
                    "end": getattr(word, 'end', word.start)
                })

        # Build sentences for each speaker
        for words_list, speaker, target_list in [
            (agent_words, "agent", agent_sentences),
            (user_words, "user", user_sentences)
        ]:
            current_sentence: List[str] = []
            sentence_start: float = 0.0
            sentence_end: float = 0.0

            for w in words_list:
                if not current_sentence:
                    sentence_start = w["start"]
                current_sentence.append(w["text"])
                sentence_end = w["end"]

                if w["text"] and w["text"][-1] in '.!?':
                    target_list.append({
                        "text": " ".join(current_sentence),
                        "start": sentence_start,
                        "end": sentence_end,
                        "speaker": speaker
                    })
                    current_sentence = []

            if current_sentence:
                target_list.append({
                    "text": " ".join(current_sentence),
                    "start": sentence_start,
                    "end": sentence_end,
                    "speaker": speaker
                })

    # Merge and sort all sentences by start time
    all_sentences = agent_sentences + user_sentences
    all_sentences.sort(key=lambda s: s["start"])

    # Merge consecutive sentences from same speaker
    conversation: List[Dict[str, str]] = []
    for sentence in all_sentences:
        if conversation and conversation[-1]["speaker"] == sentence["speaker"]:
            # Same speaker - append to existing turn
            conversation[-1]["text"] += " " + sentence["text"]
        else:
            # New speaker - new turn
            conversation.append({
                "speaker": sentence["speaker"],
                "text": sentence["text"]
            })

    # Format as [agent]: text\n\n[user]: text
    formatted_lines = []
    for turn in conversation:
        formatted_lines.append(f"[{turn['speaker']}]: {turn['text']}")

    transcript = "\n\n".join(formatted_lines)
    logger.info(f"Stitched transcript: {len(conversation)} turns, {len(transcript)} chars")

    return transcript


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True
)
def save_transcript_to_db(user_id: str, transcript: str) -> None:
    """
    Append transcript to onboarding_information table.

    If a transcript already exists, the new one is appended with a separator.
    If no row exists, creates a new one.

    Args:
        user_id: User UUID
        transcript: Formatted transcript string
    """
    supabase = get_supabase()

    logger.info(f"Saving transcript for user {user_id} ({len(transcript)} chars)")

    # Check if row exists and get current transcript
    result = supabase.table("onboarding_information").select(
        "onboarding_call_transcript"
    ).eq("user_id", user_id).execute()

    if result.data and len(result.data) > 0:
        # Row exists - append to existing transcript
        existing = result.data[0].get("onboarding_call_transcript") or ""
        if existing:
            new_transcript = existing + "\n\n---\n\n" + transcript
        else:
            new_transcript = transcript

        supabase.table("onboarding_information").update(
            {"onboarding_call_transcript": new_transcript}
        ).eq("user_id", user_id).execute()
    else:
        # No row exists - insert new
        supabase.table("onboarding_information").insert(
            {
                "user_id": user_id,
                "onboarding_call_transcript": transcript
            }
        ).execute()

    logger.info(f"Successfully saved transcript for user {user_id}")


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
def notify_n8n(user_id: str) -> None:
    """
    Notify n8n that transcription is complete.

    Args:
        user_id: User UUID
    """
    logger.info(f"Notifying n8n of transcript completion for user {user_id}")

    response = httpx.post(
        settings.n8n_persona_ideas_webhook_url,
        json={
            "identifier": "transcript_complete",
            "userId": user_id
        },
        headers={
            "Content-Type": "application/json"
        },
        timeout=30.0
    )

    response.raise_for_status()
    logger.info(f"Successfully notified n8n for user {user_id}")


def process_transcription(request_data: Dict[str, Any]) -> None:
    """
    Main job function - orchestrates the full transcription flow.

    Args:
        request_data: Request payload from webhook
    """
    user_id = request_data["userId"]
    recording_type = request_data["recordingType"]

    logger.info(f"Processing {recording_type} transcription for user {user_id}")

    # Create temp directory
    temp_dir = Path("/tmp/elevenlabs_transcription")
    temp_dir.mkdir(exist_ok=True)

    try:
        if recording_type == "dual":
            # Dual recording - download both files and combine
            mic_url = request_data["micUrl"]
            system_url = request_data["systemUrl"]

            mic_path = temp_dir / f"{user_id}_mic.webm"
            system_path = temp_dir / f"{user_id}_system.webm"
            stereo_path = temp_dir / f"{user_id}_stereo.ogg"

            # Download both files
            logger.info("Downloading mic and system recordings...")
            download_from_storage(mic_url, mic_path)
            download_from_storage(system_url, system_path)

            # Combine into stereo
            logger.info("Combining into stereo opus...")
            combine_stereo_opus(mic_path, system_path, stereo_path)

            # Transcribe
            logger.info("Transcribing with ElevenLabs multichannel...")
            result = transcribe_with_elevenlabs(stereo_path, mode="dual")

            # Cleanup temp files
            mic_path.unlink(missing_ok=True)
            system_path.unlink(missing_ok=True)
            stereo_path.unlink(missing_ok=True)

        else:
            # IRL recording - single file with diarization
            irl_url = request_data["irlUrl"]
            irl_path = temp_dir / f"{user_id}_irl.webm"

            # Download file
            logger.info("Downloading IRL recording...")
            download_from_storage(irl_url, irl_path)

            # Transcribe with diarization
            logger.info("Transcribing with ElevenLabs diarization...")
            result = transcribe_with_elevenlabs(irl_path, mode="irl")

            # Cleanup
            irl_path.unlink(missing_ok=True)

        # Stitch transcript
        logger.info("Stitching transcript...")
        transcript = stitch_transcript(result, mode=recording_type)

        # Save to database
        logger.info("Saving transcript to database...")
        save_transcript_to_db(user_id, transcript)

        # Notify n8n
        logger.info("Notifying n8n...")
        notify_n8n(user_id)

        logger.info(f"Successfully completed transcription for user {user_id}")

    except Exception as e:
        logger.error(f"Failed to process transcription for user {user_id}: {str(e)}", exc_info=True)
        raise  # Re-raise to mark job as failed in RQ
