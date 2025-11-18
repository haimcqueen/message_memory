"""Check job status in Redis."""
from redis import Redis
from rq.job import Job
from utils.config import settings

redis_conn = Redis.from_url(settings.redis_url)
job_id = 'cdaa073f-7863-4011-adb6-b76ecfb93987'

try:
    job = Job.fetch(job_id, connection=redis_conn)
    print(f"Job status: {job.get_status()}")
    print(f"Job created: {job.created_at}")
    if job.exc_info:
        print(f"Error info: {job.exc_info}")
except Exception as e:
    print(f"Error fetching job: {e}")
