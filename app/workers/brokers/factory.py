from app.workers.brokers.redis import RedisBroker
from app.workers.brokers.rabbitmq import RabbitMQBroker

class BrokerFactory:
    @staticmethod
    def get_broker(broker_name: str):
        if broker_name == "redis":
            return RedisBroker().get_broker()
        elif broker_name == "rabbitmq":
            return RabbitMQBroker().get_broker()
        else:
            raise ValueError(f"Unknown broker: {broker_name}")
