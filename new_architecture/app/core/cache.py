# app/core/cache.py

"""
Cache management module
Handles caching using Redis or in-memory storage
"""

import logging
import json
import pickle
from typing import Any, Optional, Union, Callable
from datetime import timedelta
from functools import wraps
import hashlib
import redis
from redis.exceptions import RedisError

from ..config import Config

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Cache manager for handling Redis and in-memory caching
    """

    def __init__(self, redis_url: Optional[str] = None):
        """
        Initialize cache manager

        Args:
            redis_url: Optional Redis URL. If None, uses in-memory cache
        """
        self.redis_client = None
        self.use_redis = False
        self.memory_cache = {}

        if redis_url:
            try:
                self.redis_client = redis.from_url(
                    redis_url,
                    decode_responses=False,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                    max_connections=50
                )
                # Test connection
                self.redis_client.ping()
                self.use_redis = True
                logger.info("Cache manager initialized with Redis")
            except Exception as e:
                logger.warning(
                    f"Failed to connect to Redis: {str(e)}. "
                    "Using in-memory cache instead."
                )
                self.redis_client = None
                self.use_redis = False
        else:
            logger.info("Cache manager initialized with in-memory storage")

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        try:
            if self.use_redis:
                value = self.redis_client.get(key)
                if value:
                    return pickle.loads(value)
            else:
                return self.memory_cache.get(key)
        except Exception as e:
            logger.error(f"Error getting cache key {key}: {str(e)}")
        return None

    def set(
            self,
            key: str,
            value: Any,
            ttl: Optional[int] = None
    ) -> bool:
        """
        Set value in cache

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (None for no expiration)

        Returns:
            True if successful, False otherwise
        """
        try:
            if self.use_redis:
                pickled_value = pickle.dumps(value)
                if ttl:
                    self.redis_client.setex(key, ttl, pickled_value)
                else:
                    self.redis_client.set(key, pickled_value)
            else:
                self.memory_cache[key] = value
                # Note: TTL not implemented for in-memory cache
            return True
        except Exception as e:
            logger.error(f"Error setting cache key {key}: {str(e)}")
            return False

    def delete(self, key: str) -> bool:
        """
        Delete value from cache

        Args:
            key: Cache key

        Returns:
            True if successful, False otherwise
        """
        try:
            if self.use_redis:
                self.redis_client.delete(key)
            else:
                self.memory_cache.pop(key, None)
            return True
        except Exception as e:
            logger.error(f"Error deleting cache key {key}: {str(e)}")
            return False

    def exists(self, key: str) -> bool:
        """
        Check if key exists in cache

        Args:
            key: Cache key

        Returns:
            True if key exists, False otherwise
        """
        try:
            if self.use_redis:
                return bool(self.redis_client.exists(key))
            else:
                return key in self.memory_cache
        except Exception as e:
            logger.error(f"Error checking cache key {key}: {str(e)}")
            return False

    def clear(self, pattern: Optional[str] = None) -> bool:
        """
        Clear cache entries

        Args:
            pattern: Optional pattern to match keys (Redis only)

        Returns:
            True if successful, False otherwise
        """
        try:
            if self.use_redis:
                if pattern:
                    keys = self.redis_client.keys(pattern)
                    if keys:
                        self.redis_client.delete(*keys)
                else:
                    self.redis_client.flushdb()
            else:
                if pattern:
                    # Simple pattern matching for in-memory cache
                    keys_to_delete = [
                        k for k in self.memory_cache.keys()
                        if pattern.replace("*", "") in k
                    ]
                    for key in keys_to_delete:
                        del self.memory_cache[key]
                else:
                    self.memory_cache.clear()
            return True
        except Exception as e:
            logger.error(f"Error clearing cache: {str(e)}")
            return False

    def get_ttl(self, key: str) -> Optional[int]:
        """
        Get time to live for a key

        Args:
            key: Cache key

        Returns:
            TTL in seconds or None
        """
        try:
            if self.use_redis:
                ttl = self.redis_client.ttl(key)
                return ttl if ttl > 0 else None
            else:
                # TTL not supported for in-memory cache
                return None
        except Exception as e:
            logger.error(f"Error getting TTL for key {key}: {str(e)}")
            return None

    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Increment a counter in cache

        Args:
            key: Cache key
            amount: Amount to increment by

        Returns:
            New value or None on error
        """
        try:
            if self.use_redis:
                return self.redis_client.incrby(key, amount)
            else:
                current = self.memory_cache.get(key, 0)
                new_value = current + amount
                self.memory_cache[key] = new_value
                return new_value
        except Exception as e:
            logger.error(f"Error incrementing cache key {key}: {str(e)}")
            return None

    def get_many(self, keys: list) -> dict:
        """
        Get multiple values from cache

        Args:
            keys: List of cache keys

        Returns:
            Dictionary of key-value pairs
        """
        result = {}
        try:
            if self.use_redis:
                values = self.redis_client.mget(keys)
                for key, value in zip(keys, values):
                    if value:
                        result[key] = pickle.loads(value)
            else:
                for key in keys:
                    if key in self.memory_cache:
                        result[key] = self.memory_cache[key]
        except Exception as e:
            logger.error(f"Error getting multiple cache keys: {str(e)}")
        return result

    def set_many(self, mapping: dict, ttl: Optional[int] = None) -> bool:
        """
        Set multiple values in cache

        Args:
            mapping: Dictionary of key-value pairs
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        try:
            if self.use_redis:
                pipe = self.redis_client.pipeline()
                for key, value in mapping.items():
                    pickled_value = pickle.dumps(value)
                    if ttl:
                        pipe.setex(key, ttl, pickled_value)
                    else:
                        pipe.set(key, pickled_value)
                pipe.execute()
            else:
                self.memory_cache.update(mapping)
            return True
        except Exception as e:
            logger.error(f"Error setting multiple cache keys: {str(e)}")
            return False

    def get_stats(self) -> dict:
        """
        Get cache statistics

        Returns:
            Dictionary with cache statistics
        """
        try:
            if self.use_redis:
                info = self.redis_client.info()
                return {
                    "type": "redis",
                    "connected": True,
                    "keys": self.redis_client.dbsize(),
                    "memory_used": info.get("used_memory_human", "Unknown"),
                    "hits": info.get("keyspace_hits", 0),
                    "misses": info.get("keyspace_misses", 0)
                }
            else:
                return {
                    "type": "memory",
                    "connected": True,
                    "keys": len(self.memory_cache)
                }
        except Exception as e:
            logger.error(f"Error getting cache stats: {str(e)}")
            return {
                "type": "redis" if self.use_redis else "memory",
                "connected": False,
                "error": str(e)
            }


# Global cache manager instance
cache_manager = CacheManager(settings.REDIS_URL if hasattr(settings, 'REDIS_URL') else None)


def get_cache(key: str) -> Optional[Any]:
    """
    Get value from cache

    Args:
        key: Cache key

    Returns:
        Cached value or None
    """
    return cache_manager.get(key)


def set_cache(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    """
    Set value in cache

    Args:
        key: Cache key
        value: Value to cache
        ttl: Time to live in seconds

    Returns:
        True if successful
    """
    return cache_manager.set(key, value, ttl)


def delete_cache(key: str) -> bool:
    """
    Delete value from cache

    Args:
        key: Cache key

    Returns:
        True if successful
    """
    return cache_manager.delete(key)


def clear_cache(pattern: Optional[str] = None) -> bool:
    """
    Clear cache entries

    Args:
        pattern: Optional pattern to match keys

    Returns:
        True if successful
    """
    return cache_manager.clear(pattern)


def cache_key(*args, **kwargs) -> str:
    """
    Generate cache key from arguments

    Args:
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        Cache key string
    """
    key_parts = [str(arg) for arg in args]
    key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
    key_string = ":".join(key_parts)
    return hashlib.md5(key_string.encode()).hexdigest()


def cached(
        ttl: int = 300,
        key_prefix: str = "",
        key_builder: Optional[Callable] = None
):
    """
    Decorator for caching function results

    Args:
        ttl: Time to live in seconds
        key_prefix: Prefix for cache key
        key_builder: Optional custom key builder function

    Returns:
        Decorator function

    Example:
        @cached(ttl=600, key_prefix="user")
        def get_user(user_id: int):
            return db.query(User).filter(User.id == user_id).first()
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Build cache key
            if key_builder:
                cache_key_str = key_builder(*args, **kwargs)
            else:
                cache_key_str = cache_key(*args, **kwargs)

            full_key = f"{key_prefix}:{func.__name__}:{cache_key_str}"

            # Try to get from cache
            cached_value = cache_manager.get(full_key)
            if cached_value is not None:
                logger.debug(f"Cache hit for key: {full_key}")
                return cached_value

            # Execute function and cache result
            logger.debug(f"Cache miss for key: {full_key}")
            result = func(*args, **kwargs)
            cache_manager.set(full_key, result, ttl)

            return result

        return wrapper

    return decorator


def invalidate_cache(key_prefix: str):
    """
    Decorator for invalidating cache after function execution

    Args:
        key_prefix: Prefix pattern for keys to invalidate

    Returns:
        Decorator function

    Example:
        @invalidate_cache("user:*")
        def update_user(user_id: int, data: dict):
            # Update user in database
            pass
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            # Invalidate cache after successful execution
            cache_manager.clear(f"{key_prefix}*")
            logger.debug(f"Invalidated cache with pattern: {key_prefix}*")
            return result

        return wrapper

    return decorator


class CachedProperty:
    """
    Descriptor for caching property values
    """

    def __init__(self, ttl: int = 300):
        """
        Initialize cached property

        Args:
            ttl: Time to live in seconds
        """
        self.ttl = ttl
        self.func = None

    def __call__(self, func: Callable) -> 'CachedProperty':
        """
        Decorator call

        Args:
            func: Function to wrap

        Returns:
            Self
        """
        self.func = func
        return self

    def __get__(self, obj, objtype=None):
        """
        Get property value

        Args:
            obj: Object instance
            objtype: Object type

        Returns:
            Property value
        """
        if obj is None:
            return self

        cache_key_str = f"{obj.__class__.__name__}:{id(obj)}:{self.func.__name__}"

        # Try to get from cache
        cached_value = cache_manager.get(cache_key_str)
        if cached_value is not None:
            return cached_value

        # Compute and cache value
        value = self.func(obj)
        cache_manager.set(cache_key_str, value, self.ttl)

        return value


def cache_response(ttl: int = 300):
    """
    Decorator for caching API responses

    Args:
        ttl: Time to live in seconds

    Returns:
        Decorator function

    Example:
        @app.get("/users/{user_id}")
        @cache_response(ttl=600)
        async def get_user(user_id: int):
            return {"user_id": user_id, "name": "John"}
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Build cache key from request
            request = kwargs.get('request')
            if request:
                cache_key_str = f"{request.url.path}:{request.query_params}"
            else:
                cache_key_str = cache_key(*args, **kwargs)

            full_key = f"response:{func.__name__}:{cache_key_str}"

            # Try to get from cache
            cached_response = cache_manager.get(full_key)
            if cached_response is not None:
                return cached_response

            # Execute function and cache response
            response = await func(*args, **kwargs)
            cache_manager.set(full_key, response, ttl)

            return response

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Build cache key from request
            request = kwargs.get('request')
            if request:
                cache_key_str = f"{request.url.path}:{request.query_params}"
            else:
                cache_key_str = cache_key(*args, **kwargs)

            full_key = f"response:{func.__name__}:{cache_key_str}"

            # Try to get from cache
            cached_response = cache_manager.get(full_key)
            if cached_response is not None:
                return cached_response

            # Execute function and cache response
            response = func(*args, **kwargs)
            cache_manager.set(full_key, response, ttl)

            return response

        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator