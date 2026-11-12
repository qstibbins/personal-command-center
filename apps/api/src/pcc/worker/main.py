from redis import Redis
from rq import Queue, Worker

from pcc.core.config import get_settings


def main() -> None:
    connection = Redis.from_url(get_settings().redis_url)
    worker = Worker([Queue("default", connection=connection)], connection=connection)
    worker.work()

if __name__ == "__main__":
    main()
