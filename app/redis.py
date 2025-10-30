from app.config import settings

def get_redis_connection_kwargs() -> dict:
    """Shared Redis connection configuration."""
    return {
        "host": settings.redis_host,
        "port": settings.redis_port,
        "db": settings.redis_db,
        "decode_responses": True
    }
