"""
Redis Service Layer
Handles caching, sessions, and real-time data
"""
from functools import wraps
import json
import pickle
from flask import current_app


class RedisService:
    """Redis operations wrapper"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    # ==================== CACHING ====================
    
    def cache_get(self, key):
        """Get cached value"""
        if not self.redis:
            return None
        try:
            value = self.redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            current_app.logger.error(f"Redis cache_get error: {e}")
            return None
    
    def cache_set(self, key, value, timeout=300):
        """Set cached value with timeout (default 5 minutes)"""
        if not self.redis:
            return False
        try:
            self.redis.setex(key, timeout, json.dumps(value))
            return True
        except Exception as e:
            current_app.logger.error(f"Redis cache_set error: {e}")
            return False
    
    def cache_delete(self, key):
        """Delete cached value"""
        if not self.redis:
            return False
        try:
            self.redis.delete(key)
            return True
        except Exception as e:
            current_app.logger.error(f"Redis cache_delete error: {e}")
            return False
    
    def cache_clear_pattern(self, pattern):
        """Clear all keys matching pattern"""
        if not self.redis:
            return False
        try:
            keys = self.redis.keys(pattern)
            if keys:
                self.redis.delete(*keys)
            return True
        except Exception as e:
            current_app.logger.error(f"Redis cache_clear_pattern error: {e}")
            return False
    
    # ==================== GKACH BALANCE CACHING ====================
    
    def get_gkach_balance(self, whatsapp):
        """Get cached Gkach balance"""
        if not self.redis:
            return None
        key = f"gkach:balance:{whatsapp}"
        return self.cache_get(key)
    
    def set_gkach_balance(self, whatsapp, balance, timeout=300):
        """Cache Gkach balance"""
        if not self.redis:
            return False
        key = f"gkach:balance:{whatsapp}"
        return self.cache_set(key, balance, timeout)
    
    def invalidate_gkach_balance(self, whatsapp):
        """Invalidate Gkach balance cache"""
        if not self.redis:
            return False
        key = f"gkach:balance:{whatsapp}"
        return self.cache_delete(key)
    
    # ==================== AD CACHING ====================
    
    def get_approved_ads(self):
        """Get cached approved ads"""
        if not self.redis:
            return None
        key = "ads:approved"
        return self.cache_get(key)
    
    def set_approved_ads(self, ads_data, timeout=600):
        """Cache approved ads (10 minutes)"""
        if not self.redis:
            return False
        key = "ads:approved"
        return self.cache_set(key, ads_data, timeout)
    
    def invalidate_approved_ads(self):
        """Invalidate approved ads cache"""
        if not self.redis:
            return False
        key = "ads:approved"
        return self.cache_delete(key)
    
    # ==================== RATE LIMITING ====================
    
    def check_rate_limit(self, key, limit, window):
        """
        Check rate limit using sliding window
        Returns: (allowed: bool, remaining: int)
        """
        if not self.redis:
            return True, limit
        try:
            current = self.redis.incr(key)
            if current == 1:
                self.redis.expire(key, window)
            
            if current > limit:
                return False, limit
            
            return True, limit - current
        except Exception as e:
            current_app.logger.error(f"Redis rate_limit error: {e}")
            return True, limit  # Fail open
    
    # ==================== COUNTERS ====================
    
    def increment_counter(self, key, amount=1):
        """Increment counter"""
        if not self.redis:
            return None
        try:
            return self.redis.incr(key, amount)
        except Exception as e:
            current_app.logger.error(f"Redis increment error: {e}")
            return None
    
    def get_counter(self, key):
        """Get counter value"""
        if not self.redis:
            return 0
        try:
            value = self.redis.get(key)
            return int(value) if value else 0
        except Exception as e:
            current_app.logger.error(f"Redis get_counter error: {e}")
            return 0
    
    # ==================== SESSIONS ====================
    
    def set_session(self, session_id, data, timeout=86400):
        """Store session data (24 hours default)"""
        if not self.redis:
            return False
        key = f"session:{session_id}"
        try:
            self.redis.setex(key, timeout, pickle.dumps(data))
            return True
        except Exception as e:
            current_app.logger.error(f"Redis set_session error: {e}")
            return False
    
    def get_session(self, session_id):
        """Get session data"""
        if not self.redis:
            return None
        key = f"session:{session_id}"
        try:
            data = self.redis.get(key)
            return pickle.loads(data) if data else None
        except Exception as e:
            current_app.logger.error(f"Redis get_session error: {e}")
            return None
    
    def delete_session(self, session_id):
        """Delete session"""
        if not self.redis:
            return False
        key = f"session:{session_id}"
        return self.cache_delete(key)
    
    # ==================== REAL-TIME DATA ====================
    
    def publish(self, channel, message):
        """Publish message to channel"""
        if not self.redis:
            return False
        try:
            self.redis.publish(channel, json.dumps(message))
            return True
        except Exception as e:
            current_app.logger.error(f"Redis publish error: {e}")
            return False
    
    def subscribe(self, channel):
        """Subscribe to channel"""
        if not self.redis:
            return None
        try:
            pubsub = self.redis.pubsub()
            pubsub.subscribe(channel)
            return pubsub
        except Exception as e:
            current_app.logger.error(f"Redis subscribe error: {e}")
            return None
    
    # ==================== LEADERBOARD ====================
    
    def add_to_leaderboard(self, leaderboard_key, member, score):
        """Add member to sorted set leaderboard"""
        if not self.redis:
            return False
        try:
            self.redis.zadd(leaderboard_key, {member: score})
            return True
        except Exception as e:
            current_app.logger.error(f"Redis leaderboard add error: {e}")
            return False
    
    def get_leaderboard(self, leaderboard_key, start=0, end=-1, reverse=True):
        """Get leaderboard rankings"""
        if not self.redis:
            return []
        try:
            if reverse:
                return self.redis.zrevrange(leaderboard_key, start, end, withscores=True)
            return self.redis.zrange(leaderboard_key, start, end, withscores=True)
        except Exception as e:
            current_app.logger.error(f"Redis leaderboard get error: {e}")
            return []
    
    # ==================== HEALTH CHECK ====================
    
    def ping(self):
        """Check Redis connection"""
        if not self.redis:
            return False
        try:
            return self.redis.ping()
        except Exception as e:
            current_app.logger.error(f"Redis ping error: {e}")
            return False


# Decorator for caching function results
def cached(timeout=300, key_prefix='view'):
    """
    Decorator to cache function results in Redis
    Usage:
        @cached(timeout=600, key_prefix='user_profile')
        def get_user_profile(user_id):
            return expensive_query(user_id)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from app import redis_client
            redis_service = RedisService(redis_client)
            
            # Generate cache key
            cache_key = f"{key_prefix}:{f.__name__}:{str(args)}:{str(kwargs)}"
            
            # Try to get from cache
            cached_result = redis_service.cache_get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Execute function
            result = f(*args, **kwargs)
            
            # Cache result
            redis_service.cache_set(cache_key, result, timeout)
            
            return result
        return decorated_function
    return decorator
