"""
Test script to verify document processing flow and n8n batching.

This script tests three scenarios:
1. Normal PDF document (<50MB) - should trigger n8n
2. Oversized document (>50MB) - should NOT trigger n8n
3. Video message - should trigger n8n with notification
"""

import os
import sys
import json
from unittest.mock import Mock, patch, call
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from workers.jobs import process_whatsapp_message


def create_document_webhook(file_size_mb: float, message_type: str = "document"):
    """Create a mock webhook payload for a document."""
    file_size_bytes = int(file_size_mb * 1024 * 1024)

    return {
        "id": f"test_msg_{file_size_mb}mb",
        "type": message_type,
        "chat_id": "1234567890@s.whatsapp.net",
        "from_me": False,
        "from": "1234567890",
        "timestamp": 1700000000,
        message_type: {
            "id": f"media_id_{file_size_mb}mb",
            "mime_type": "application/pdf" if message_type == "document" else "video/mp4",
            "caption": f"Test {message_type}",
            "file_size": file_size_bytes
        }
    }


def test_normal_document():
    """Test normal document (<50MB) - should call n8n."""
    print("\n" + "="*80)
    print("TEST 1: Normal PDF Document (10MB) - Should trigger n8n")
    print("="*80)

    webhook_data = create_document_webhook(10.0)

    with patch('workers.jobs.send_presence') as mock_presence, \
         patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
         patch('workers.jobs.process_media_message') as mock_media, \
         patch('workers.jobs.insert_message') as mock_insert, \
         patch('workers.jobs.get_user_id_by_phone') as mock_user_id, \
         patch('workers.jobs.detect_session') as mock_session, \
         patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

        # Setup mocks
        mock_user_id.return_value = "user-123"
        mock_session.return_value = "session-456"
        mock_media.return_value = ("https://storage.url/file.pdf", "parsed content")

        # Execute
        process_whatsapp_message(webhook_data)

        # Verify
        print("\n✓ Typing presence called:", mock_presence.called)
        print("✓ Notification sent:", mock_send_msg.called)
        if mock_send_msg.called:
            print(f"  Message: {mock_send_msg.call_args[0][1]}")
        print("✓ Media processed:", mock_media.called)
        print("✓ Message inserted to DB:", mock_insert.called)
        print("✓ n8n batch called:", mock_n8n_batch.called)

        if mock_n8n_batch.called:
            print("  ✅ SUCCESS: n8n batching WAS triggered for normal document")
        else:
            print("  ❌ FAIL: n8n batching was NOT triggered for normal document")

        return mock_n8n_batch.called


def test_oversized_document():
    """Test oversized document (>50MB) - should NOT call n8n."""
    print("\n" + "="*80)
    print("TEST 2: Oversized PDF Document (100MB) - Should NOT trigger n8n")
    print("="*80)

    webhook_data = create_document_webhook(100.0)

    with patch('workers.jobs.send_presence') as mock_presence, \
         patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
         patch('workers.jobs.insert_message') as mock_insert, \
         patch('workers.jobs.get_user_id_by_phone') as mock_user_id, \
         patch('workers.jobs.detect_session') as mock_session, \
         patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

        # Setup mocks
        mock_user_id.return_value = "user-123"
        mock_session.return_value = "session-456"

        # Execute
        process_whatsapp_message(webhook_data)

        # Verify
        print("\n✓ Typing presence called:", mock_presence.called)
        print("✓ Rejection notification sent:", mock_send_msg.called)
        if mock_send_msg.called:
            print(f"  Message: {mock_send_msg.call_args[0][1]}")
        print("✓ Message inserted to DB:", mock_insert.called)
        print("✓ n8n batch called:", mock_n8n_batch.called)

        if not mock_n8n_batch.called:
            print("  ✅ SUCCESS: n8n batching was NOT triggered for oversized document")
        else:
            print("  ❌ FAIL: n8n batching WAS triggered for oversized document (should skip)")

        return not mock_n8n_batch.called


def test_video_message():
    """Test video message - should call n8n with video notification."""
    print("\n" + "="*80)
    print("TEST 3: Video Message - Should trigger n8n with notification")
    print("="*80)

    webhook_data = create_document_webhook(5.0, message_type="video")

    with patch('workers.jobs.send_presence') as mock_presence, \
         patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
         patch('workers.jobs.process_media_message') as mock_media, \
         patch('workers.jobs.insert_message') as mock_insert, \
         patch('workers.jobs.get_user_id_by_phone') as mock_user_id, \
         patch('workers.jobs.detect_session') as mock_session, \
         patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

        # Setup mocks
        mock_user_id.return_value = "user-123"
        mock_session.return_value = "session-456"
        mock_media.return_value = ("https://storage.url/video.mp4", None)

        # Execute
        process_whatsapp_message(webhook_data)

        # Verify
        print("\n✓ Typing presence called:", mock_presence.called)
        print("✓ Video notification sent:", mock_send_msg.called)
        if mock_send_msg.called:
            print(f"  Message: {mock_send_msg.call_args[0][1]}")
        print("✓ Media processed:", mock_media.called)
        print("✓ Message inserted to DB:", mock_insert.called)
        print("✓ n8n batch called:", mock_n8n_batch.called)

        if mock_n8n_batch.called:
            print("  ✅ SUCCESS: n8n batching WAS triggered for video")
        else:
            print("  ❌ FAIL: n8n batching was NOT triggered for video")

        return mock_n8n_batch.called


if __name__ == "__main__":
    print("\n" + "="*80)
    print("DOCUMENT PROCESSING AND N8N BATCHING TEST SUITE")
    print("="*80)

    results = []

    # Run tests
    results.append(("Normal Document (10MB)", test_normal_document()))
    results.append(("Oversized Document (100MB)", test_oversized_document()))
    results.append(("Video Message", test_video_message()))

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed!")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        sys.exit(1)
