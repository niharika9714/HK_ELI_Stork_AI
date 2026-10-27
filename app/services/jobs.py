import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor


class Jobs:
    """Bounded single-process prototype; results never cross user ownership."""
    def __init__(self, workers, capacity, ttl):
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='hkeli')
        self.capacity, self.ttl = capacity, ttl
        self.lock, self.items = threading.Lock(), {}

    def submit(self, owner, function):
        with self.lock:
            now = time.monotonic()
            self.items = {k: v for k, v in self.items.items() if not v[2].done() or v[1] > now}
            if len(self.items) >= self.capacity:
                raise OverflowError('Analysis capacity is busy; please retry later.')
            key = secrets.token_urlsafe(24)
            self.items[key] = (owner, now + self.ttl, self.pool.submit(function))
            return key

    def get(self, owner, key):
        with self.lock:
            item = self.items.get(key)
            if not item or item[0] != owner:
                raise KeyError('Job not found.')
            if item[1] < time.monotonic() and item[2].done():
                del self.items[key]
                raise KeyError('Job expired.')
            future = item[2]
        if not future.done():
            return {'status': 'pending'}
        try:
            return {'status': 'completed', 'answer': future.result()}
        except PermissionError as error:
            return {'status': 'failed', 'code': 'access_denied', 'message': str(error)}
        except ValueError as error:
            return {'status': 'failed', 'code': 'missing_data_or_unsupported_operation', 'message': str(error)}
        except Exception:
            return {'status': 'failed', 'code': 'integration_failed', 'message': 'The integration or calculation failed. No substitute chart was produced.'}
