import time, inspect, sys, array, traceback
from fastapi import HTTPException, status
from collections import OrderedDict
from types import GeneratorType
from datetime import datetime
from functools import wraps
from bson import ObjectId

def _response(document):
    """
    Recursively convert ObjectId instances to strings in a document.
    """
    if isinstance(document, dict):
        return {k: _response(v) for k, v in document.items()}
    elif isinstance(document, list):
        return [_response(item) for item in document]
    elif isinstance(document, ObjectId):
        return str(document)
    else:
        return document

def validate_object_id(oid: str) -> ObjectId:
    """Return an ObjectId or raise 422 if malformed."""
    try:
        return ObjectId(oid)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid ObjectId format"
        )

def make_hashable(obj):
    """
    Recursively convert mutable objects to hashable types for all Python native types.
    
    Handles: list, tuple, dict, set, frozenset, bytearray, array.array, 
    memoryview, range, generators, and all other hashable types.
    """
    # Handle None and basic hashable types first (most common case)
    if obj is None or isinstance(obj, (int, float, str, bytes, bool, complex, type(None))):
        return obj
    
    # Handle already hashable types (frozenset, tuple of hashables, etc.)
    try:
        hash(obj)
        return obj
    except TypeError:
        pass  # Continue to handle unhashable types
    
    # Handle collections
    if isinstance(obj, (list, tuple)):
        return tuple(make_hashable(item) for item in obj)
    
    if isinstance(obj, dict):
        return tuple(sorted((make_hashable(k), make_hashable(v)) for k, v in obj.items()))
    
    if isinstance(obj, set):
        return frozenset(make_hashable(item) for item in obj)
    
    if isinstance(obj, frozenset):
        return frozenset(make_hashable(item) for item in obj)
    
    # Handle byte-like objects
    if isinstance(obj, bytearray):
        return bytes(obj)
    
    if isinstance(obj, memoryview):
        return bytes(obj)
    
    # Handle array.array
    if isinstance(obj, array.array):
        return (obj.typecode, tuple(obj))
    
    # Handle range objects
    if isinstance(obj, range):
        return ('range', obj.start, obj.stop, obj.step)
    
    # Handle generators and iterators (consume them - use with caution!)
    if isinstance(obj, (GeneratorType, map, filter, zip, enumerate)):
        return tuple(make_hashable(item) for item in obj)
    
    # Handle other iterator types by attempting to convert to tuple
    if hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes)):
        try:
            return tuple(make_hashable(item) for item in obj)
        except (TypeError, ValueError):
            pass
    
    # For objects with __dict__ (custom classes), use their attributes
    if hasattr(obj, '__dict__'):
        return ('__dict__', tuple(sorted((k, make_hashable(v)) for k, v in obj.__dict__.items())))
    
    # For objects with __slots__, try to get their values
    if hasattr(obj, '__slots__'):
        slot_values = []
        for slot in obj.__slots__:
            if hasattr(obj, slot):
                slot_values.append((slot, make_hashable(getattr(obj, slot))))
        return ('__slots__', tuple(sorted(slot_values)))
    
    # Fallback: use string representation (not ideal but works)
    # Include type name to distinguish between objects with same repr
    return (type(obj).__name__, str(obj))

def timed_lru_cache(max_size: int, minutes: float):
    """
    A decorator that caches function results (sync or async) up to a maximum
    size and discards them after a specified number of minutes.

    Args:
        max_size (int): Maximum number of items to cache.
        minutes (float): Time in minutes after which cached items expire.

    Returns:
        Decorator function.
    """
    def decorator(func):
        cache = OrderedDict()
        expiration_time = minutes * 60  # Convert minutes to seconds
        is_async = inspect.iscoroutinefunction(func)

        def _clear_expired():
            """Helper to remove expired items from cache."""
            current_time = time.time()
            # Iterate over a copy of keys to allow modification during iteration.
            # No early exit: the order is least-recently-used, not insertion time,
            # so expired items may sit behind fresh ones.
            for k in list(cache.keys()):
                cached_time, _ = cache[k]
                if current_time - cached_time > expiration_time:
                    cache.pop(k, None)

        def _update_cache(key, result):
             """Helper to update cache and enforce size limit."""
             current_time = time.time()
             cache[key] = (current_time, result)
             cache.move_to_end(key) # Mark as recently used

             # Enforce max size
             if len(cache) > max_size:
                 cache.popitem(last=False) # Remove the oldest item

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                key = (make_hashable(args), make_hashable(kwargs))
            except Exception as e:
                # If we can't make the arguments hashable, don't cache
                return func(*args, **kwargs)
            
            _clear_expired()

            if key in cache:
                cache.move_to_end(key)
                _, result = cache[key]
                return result

            result = func(*args, **kwargs)
            _update_cache(key, result)
            return result

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                key = (make_hashable(args), make_hashable(kwargs))
            except Exception as e:
                # If we can't make the arguments hashable, don't cache
                return await func(*args, **kwargs)
            
            _clear_expired()

            if key in cache:
                cache.move_to_end(key)
                _, result = cache[key]
                return result

            # Await the async function
            result = await func(*args, **kwargs)
            _update_cache(key, result)
            return result

        # Add cache inspection methods
        def cache_info():
            """Return cache statistics."""
            return {
                'size': len(cache),
                'max_size': max_size,
                'expiration_minutes': minutes,
                'keys': list(cache.keys())
            }
        
        def cache_clear():
            """Clear the cache."""
            cache.clear()

        wrapper = async_wrapper if is_async else sync_wrapper
        wrapper.cache_info = cache_info
        wrapper.cache_clear = cache_clear
        
        return wrapper
    return decorator

def current_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log_exception():
    exc_type, _, _ = sys.exc_info()

    frame = inspect.currentframe().f_back
    func_name = frame.f_code.co_name
    filename = frame.f_code.co_filename
    line_no = frame.f_lineno

    detailed_exp = traceback.format_exc()
    msg = (
        f"{current_timestamp()} "
        f"~ Error (Log call: [{filename}.{func_name}():{line_no}])\n"
        f"Stack: {detailed_exp}\n"
    )

    if not issubclass(exc_type, HTTPException):
        print(msg)

    return msg
