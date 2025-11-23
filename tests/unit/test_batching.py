"""
Unit tests for workers.batching module.

These tests verify the message batching logic for n8n webhook forwarding.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from workers.batching import add_message_to_batch, process_and_forward_batch


@pytest.fixture
def mock_redis_conn():
    """Mock Redis connection."""
    redis_mock = Mock()
    redis_mock.get.return_value = None
    redis_mock.set.return_value = True
    redis_mock.exists.return_value = False
    redis_mock.incr.return_value = 1
    redis_mock.delete.return_value = 1
    return redis_mock


@pytest.fixture
def mock_queue():
    """Mock RQ Queue."""
    queue_mock = Mock()
    job_mock = Mock()
    job_mock.id = "test-job-123"
    queue_mock.enqueue_in.return_value = job_mock
    return queue_mock


class TestAddMessageToBatch:
    """Tests for add_message_to_batch function."""

    @pytest.mark.unit
    def test_first_message_in_batch(self, mock_redis_conn, mock_queue):
        """Test adding the first message to a new batch."""
        chat_id = "1234567890@s.whatsapp.net"
        content = "Hello"
        user_id = "user-123"

        with patch('workers.batching.get_redis_connection', return_value=mock_redis_conn), \
             patch('workers.batching.Queue', return_value=mock_queue):

            add_message_to_batch(chat_id, content, user_id)

            # Should increment counter
            assert mock_redis_conn.incr.called
            assert "n8n_count:" in str(mock_redis_conn.incr.call_args)

            # Should store user_id
            assert mock_redis_conn.set.called
            user_id_calls = [call for call in mock_redis_conn.set.call_args_list
                           if "n8n_user:" in str(call)]
            assert len(user_id_calls) > 0

            # Should schedule new job
            assert mock_queue.enqueue_in.called

            # Should store job ID
            job_id_calls = [call for call in mock_redis_conn.set.call_args_list
                          if "n8n_job:" in str(call)]
            assert len(job_id_calls) > 0

    @pytest.mark.unit
    def test_subsequent_message_reschedules_job(self, mock_redis_conn, mock_queue):
        """Test that adding a new message cancels the existing job and schedules a new one."""
        chat_id = "1234567890@s.whatsapp.net"
        content = "Second message"
        user_id = "user-123"

        # Simulate existing job
        existing_job_id = b"existing-job-456"
        mock_redis_conn.get.return_value = existing_job_id

        existing_job_mock = Mock()
        existing_job_mock.get_status.return_value = "scheduled"

        with patch('workers.batching.get_redis_connection', return_value=mock_redis_conn), \
             patch('workers.batching.Queue', return_value=mock_queue), \
             patch('workers.batching.Job.fetch', return_value=existing_job_mock):

            add_message_to_batch(chat_id, content, user_id)

            # Should cancel existing job
            assert existing_job_mock.cancel.called

            # Should schedule new job
            assert mock_queue.enqueue_in.called

    @pytest.mark.unit
    def test_batch_counter_increments(self, mock_redis_conn, mock_queue):
        """Test that message counter increments correctly."""
        chat_id = "1234567890@s.whatsapp.net"

        # Simulate counter incrementing
        mock_redis_conn.incr.side_effect = [1, 2, 3]

        with patch('workers.batching.get_redis_connection', return_value=mock_redis_conn), \
             patch('workers.batching.Queue', return_value=mock_queue):

            # Add three messages
            add_message_to_batch(chat_id, "Message 1", "user-123")
            add_message_to_batch(chat_id, "Message 2", "user-123")
            add_message_to_batch(chat_id, "Message 3", "user-123")

            # Incr should be called 3 times
            assert mock_redis_conn.incr.call_count == 3

    @pytest.mark.unit
    def test_user_id_stored_in_redis(self, mock_redis_conn, mock_queue):
        """Test that user_id is stored in Redis."""
        chat_id = "1234567890@s.whatsapp.net"
        user_id = "user-456"

        with patch('workers.batching.get_redis_connection', return_value=mock_redis_conn), \
             patch('workers.batching.Queue', return_value=mock_queue):

            add_message_to_batch(chat_id, "Test", user_id)

            # Find the user_id set call
            user_id_calls = [call for call in mock_redis_conn.set.call_args_list
                           if "n8n_user:" in str(call) and user_id in str(call)]
            assert len(user_id_calls) > 0


class TestProcessAndForwardBatch:
    """Tests for process_and_forward_batch function."""

    @pytest.mark.unit
    def test_successful_batch_processing(self, mock_redis_conn):
        """Test successful batch processing and forwarding to n8n."""
        chat_id = "1234567890@s.whatsapp.net"

        # Mock Redis returns
        mock_redis_conn.get.side_effect = [
            b"1234567890.0",  # start_time_key
            b"5",             # count_key (5 messages)
            b"user-123"       # user_id_key
        ]

        with patch('workers.batching.get_redis_connection', return_value=mock_redis_conn), \
             patch('workers.n8n_forwarder.safe_forward_to_n8n') as mock_forward, \
             patch('workers.batching.time.time', return_value=1234567895.0):

            process_and_forward_batch(chat_id)

            # Should forward to n8n with correct payload
            assert mock_forward.called
            payload = mock_forward.call_args[0][0]
            assert payload["user_id"] == "user-123"
            assert payload["batched_message_count"] == 5

            # Should clear batch data from Redis
            assert mock_redis_conn.delete.call_count >= 4  # count, user_id, job_id, start_time

    @pytest.mark.unit
    def test_batch_with_no_messages(self, mock_redis_conn):
        """Test batch processing when there are no messages."""
        chat_id = "1234567890@s.whatsapp.net"

        # Mock Redis to return None for message count
        mock_redis_conn.get.return_value = None

        with patch('workers.batching.get_redis_connection', return_value=mock_redis_conn), \
             patch('workers.n8n_forwarder.safe_forward_to_n8n') as mock_forward:

            process_and_forward_batch(chat_id)

            # Should NOT forward to n8n
            assert not mock_forward.called

            # Should NOT try to delete anything
            assert not mock_redis_conn.delete.called

    @pytest.mark.unit
    def test_batch_without_user_id(self, mock_redis_conn):
        """Test batch processing when user_id is not set."""
        chat_id = "1234567890@s.whatsapp.net"

        # Mock Redis returns
        mock_redis_conn.get.side_effect = [
            b"1234567890.0",  # start_time_key
            b"3",             # count_key (3 messages)
            None              # user_id_key (no user_id)
        ]

        with patch('workers.batching.get_redis_connection', return_value=mock_redis_conn), \
             patch('workers.n8n_forwarder.safe_forward_to_n8n') as mock_forward, \
             patch('workers.batching.time.time', return_value=1234567893.0):

            process_and_forward_batch(chat_id)

            # Should forward with None user_id
            assert mock_forward.called
            payload = mock_forward.call_args[0][0]
            assert payload["user_id"] is None
            assert payload["batched_message_count"] == 3

    @pytest.mark.unit
    def test_batch_timing_calculation(self, mock_redis_conn):
        """Test that batch calculates timing correctly."""
        chat_id = "1234567890@s.whatsapp.net"

        start_time = 1234567890.0
        end_time = 1234567950.0  # 60 seconds later

        mock_redis_conn.get.side_effect = [
            str(start_time).encode(),  # start_time_key
            b"10",                     # count_key
            b"user-123"                # user_id_key
        ]

        with patch('workers.batching.get_redis_connection', return_value=mock_redis_conn), \
             patch('workers.n8n_forwarder.safe_forward_to_n8n') as mock_forward, \
             patch('workers.batching.time.time', return_value=end_time):

            process_and_forward_batch(chat_id)

            # Timing should be logged (check via forward being called)
            assert mock_forward.called

    @pytest.mark.unit
    def test_batch_forwards_correct_payload_structure(self, mock_redis_conn):
        """Test that the payload sent to n8n has the correct structure."""
        chat_id = "1234567890@s.whatsapp.net"

        mock_redis_conn.get.side_effect = [
            b"1234567890.0",  # start_time_key
            b"7",             # count_key
            b"user-789"       # user_id_key
        ]

        with patch('workers.batching.get_redis_connection', return_value=mock_redis_conn), \
             patch('workers.n8n_forwarder.safe_forward_to_n8n') as mock_forward, \
             patch('workers.batching.time.time', return_value=1234567895.0):

            process_and_forward_batch(chat_id)

            # Verify payload structure
            assert mock_forward.called
            payload = mock_forward.call_args[0][0]

            # Should have exactly these keys
            assert set(payload.keys()) == {"user_id", "batched_message_count"}
            assert payload["user_id"] == "user-789"
            assert payload["batched_message_count"] == 7

    @pytest.mark.unit
    def test_batch_clears_redis_keys_on_success(self, mock_redis_conn):
        """Test that all Redis keys are cleared after successful forward."""
        chat_id = "1234567890@s.whatsapp.net"

        mock_redis_conn.get.side_effect = [
            b"1234567890.0",
            b"5",
            b"user-123"
        ]

        with patch('workers.batching.get_redis_connection', return_value=mock_redis_conn), \
             patch('workers.n8n_forwarder.safe_forward_to_n8n') as mock_forward, \
             patch('workers.batching.time.time', return_value=1234567895.0):

            process_and_forward_batch(chat_id)

            # Should delete all 4 keys: count, user_id, job_id, start_time
            assert mock_redis_conn.delete.call_count == 4

            # Verify the keys being deleted contain the chat_id
            delete_calls = mock_redis_conn.delete.call_args_list
            for call in delete_calls:
                assert chat_id in str(call)

    @pytest.mark.unit
    def test_batch_handles_n8n_failure_gracefully(self, mock_redis_conn):
        """Test that batch processing doesn't re-raise n8n forwarding exceptions."""
        chat_id = "1234567890@s.whatsapp.net"

        mock_redis_conn.get.side_effect = [
            b"1234567890.0",
            b"5",
            b"user-123"
        ]

        with patch('workers.batching.get_redis_connection', return_value=mock_redis_conn), \
             patch('workers.n8n_forwarder.safe_forward_to_n8n') as mock_forward, \
             patch('workers.batching.time.time', return_value=1234567895.0):

            # Make n8n forward raise an exception
            mock_forward.side_effect = Exception("n8n is down")

            # Should NOT raise exception
            process_and_forward_batch(chat_id)

            # Should still try to forward
            assert mock_forward.called
