from app.workers.brokers.base import Broker

class RabbitMQBroker(Broker):
    def get_broker(self):
        raise NotImplementedError("RabbitMQ broker is not implemented yet.")
