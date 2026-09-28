import os

import redis


def get_redis_client():
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        client = redis.Redis.from_url(url, decode_responses=True)
        client.ping()
        return client
    except redis.RedisError:
        return None
