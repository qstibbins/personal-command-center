from redis import Redis
from rq import Queue
from pcc.core.config import get_settings
from pcc.worker.jobs import sample_job

if __name__ == "__main__":
    q = Queue("default", connection=Redis.from_url(get_settings().redis_url))
    job = q.enqueue(sample_job)
    print(f"Enqueued {job.id}. Run a worker to process it.")
