import time, inspect, sys, array, traceback, os
from fastapi import HTTPException, status
from collections import OrderedDict
from pathlib import Path
import cloudpickle
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
    
    # For objects with __dict__ (custom classes), use their attributes.
    # The type name is part of the key, so two classes that happen to share
    # field names do not collide in the same cache.
    if hasattr(obj, '__dict__'):
        return (type(obj).__name__, tuple(sorted((k, make_hashable(v)) for k, v in obj.__dict__.items())))
    
    # For objects with __slots__, try to get their values
    if hasattr(obj, '__slots__'):
        slot_values = []
        for slot in obj.__slots__:
            if hasattr(obj, slot):
                slot_values.append((slot, make_hashable(getattr(obj, slot))))
        return (type(obj).__name__, tuple(sorted(slot_values)))
    
    # Fallback: use string representation (not ideal but works)
    # Include type name to distinguish between objects with same repr
    return (type(obj).__name__, str(obj))

def _cache_decorator(max_size: int, seconds: float | None, persist: str | None):
    """Shared core for the cache decorators below.

    Keys go through make_hashable, so unhashable arguments (dict, list, set,
    arbitrary objects) are cacheable. Wraps sync and async functions alike.
    """
    def decorator(func):
        cache: OrderedDict = OrderedDict()
        path = Path(persist) if persist else None
        is_async = inspect.iscoroutinefunction(func)

        def _expired(stamp: float) -> bool:
            return seconds is not None and time.time() - stamp > seconds

        if path and path.exists():
            try:
                cache.update(cloudpickle.loads(path.read_bytes()))
                for k in [k for k, (stamp, _) in cache.items() if _expired(stamp)]:
                    cache.pop(k, None)
            except Exception:
                # A corrupt or unreadable cache file is not worth failing over
                pass

        warned = False

        def _save():
            """Persistence is best-effort - an unwritable path or an unpicklable
            value degrades to an in-memory cache rather than failing the call.
            It says so once, so a silently broken cache file is noticeable."""
            nonlocal warned
            if not path:
                return
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
                tmp.write_bytes(cloudpickle.dumps(cache))
                os.replace(tmp, path)   # atomic, so a reader never sees half a file
            except Exception as exc:
                if not warned:
                    warned = True
                    print(f"{current_timestamp()} ~ cache persistence disabled for "
                          f"{func.__name__} ({path}): {exc}")

        def _lookup(key):
            """Return a 1-tuple on a hit, so a cached None is still a hit."""
            entry = cache.get(key)
            if entry is None:
                return None
            stamp, value = entry
            if _expired(stamp):
                cache.pop(key, None)
                return None
            cache.move_to_end(key)
            return (value,)

        # tradeoff: re-pickles the whole dict per write and is per-process, so
        # workers keep separate files. Move to Redis if the cache gets big or
        # has to be shared.
        def _store(key, value):
            cache[key] = (time.time(), value)
            cache.move_to_end(key)
            if len(cache) > max_size:
                cache.popitem(last=False)
            _save()

        def _key(args, kwargs):
            return (make_hashable(args), make_hashable(kwargs))

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                key = _key(args, kwargs)
            except Exception:
                return func(*args, **kwargs)   # unkeyable, so skip the cache

            hit = _lookup(key)
            if hit is not None:
                return hit[0]

            result = func(*args, **kwargs)
            _store(key, result)
            return result

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                key = _key(args, kwargs)
            except Exception:
                return await func(*args, **kwargs)

            hit = _lookup(key)
            if hit is not None:
                return hit[0]

            result = await func(*args, **kwargs)
            _store(key, result)
            return result

        def cache_info():
            return {
                'size': len(cache),
                'max_size': max_size,
                'expiration_seconds': seconds,
                'persist': str(path) if path else None
            }

        def cache_clear():
            cache.clear()
            if path:
                path.unlink(missing_ok=True)

        wrapper = async_wrapper if is_async else sync_wrapper
        wrapper.cache_info = cache_info
        wrapper.cache_clear = cache_clear
        return wrapper

    return decorator

def timed_lru_cache(max_size: int, minutes: float, persist: str | None = None):
    """Cache results (sync or async) up to max_size, expiring after `minutes`.

    Pass persist="path/to/file.pkl" to keep the cache across restarts; entry
    ages are stored too, so expiry survives a restart.
    """
    return _cache_decorator(max_size, minutes * 60, persist)

def flexible_lru_cache(max_size: int = 128, persist: str | None = None):
    """LRU cache with no expiry that accepts *any* argument type.

    functools.lru_cache raises TypeError on a dict, list, set or plain object;
    this one keys on make_hashable(args), so those all work.
    """
    return _cache_decorator(max_size, None, persist)

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
