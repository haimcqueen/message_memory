"""Inspect job payload from Redis."""
import json
from redis import Redis
from rq.job import Job
from utils.config import settings

redis_conn = Redis.from_url(settings.redis_url)
job_id = 'cdaa073f-7863-4011-adb6-b76ecfb93987'

try:
    job = Job.fetch(job_id, connection=redis_conn)
    print("=" * 80)
    print("RAW LINK_PREVIEW MESSAGE PAYLOAD:")
    print("=" * 80)
    if job.args:
        message_data = job.args[0]
        print(json.dumps(message_data, indent=2))
    else:
        print("No args found")
except Exception as e:
    print(f"Error: {e}")
