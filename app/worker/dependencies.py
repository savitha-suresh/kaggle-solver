from app.llm.factory import llm_factory
from app.llm.base import BaseLLM
import redis.asyncio as redis
from app.redis import get_redis_connection_kwargs
from app.storage.factory import storage_factory
from app.storage.base import BaseStorage

class LLMClientDependency:
    _instance: BaseLLM | None = None

    @classmethod
    def get_client(cls) -> BaseLLM:
        if cls._instance is None:
            cls._instance = llm_factory.get_llm()
        return cls._instance

def get_llm_client() -> BaseLLM:
    return LLMClientDependency.get_client()

class RedisClientDependency:
    _instance: redis.Redis | None = None

    @classmethod
    def get_client(cls) -> redis.Redis:
        if cls._instance is None:
            cls._instance = redis.Redis(**get_redis_connection_kwargs())
        return cls._instance

def get_redis_client() -> redis.Redis:
    return RedisClientDependency.get_client()

class StorageClientDependency:
    _instance: BaseStorage | None = None

    @classmethod
    def get_client(cls) -> BaseStorage:
        if cls._instance is None:
            cls._instance = storage_factory.get_storage()
        return cls._instance

def get_storage_client() -> BaseStorage:
    return StorageClientDependency.get_client()
