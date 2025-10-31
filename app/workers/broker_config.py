from app.workers.brokers.factory import BrokerFactory
from app.config import settings

broker = BrokerFactory.get_broker(settings.broker_provider)