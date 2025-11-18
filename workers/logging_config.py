"""
Logging configuration for RQ worker processes.

This module initializes Python logging for worker processes.
Import this module at the top of any worker entry point to ensure
logging is properly configured before any jobs execute.
"""
import logging
import sys

# Configure logging for worker processes
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,  # Ensure logs go to stdout for Railway
    force=True  # Override any existing configuration
)

# Get root logger
logger = logging.getLogger(__name__)
logger.info("Worker logging configuration initialized")
