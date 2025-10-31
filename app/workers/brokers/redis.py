from taskiq_redis import RedisAsyncResultBackend, ListQueueBroker
from app.workers.brokers.base import Broker

class RedisBroker(Broker):
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url

    def get_broker(self):
        result_backend = RedisAsyncResultBackend(
            redis_url=self.redis_url,
        )

        broker = ListQueueBroker(
            url=self.redis_url
        ).with_result_backend(result_backend)
        return broker
