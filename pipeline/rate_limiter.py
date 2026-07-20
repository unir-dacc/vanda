import threading
import time


class NCBIRateLimiter:
	"""Rate limiter thread-safe para NCBI Entrez API.

	NCBI permite 3 req/s sem API key, 10 req/s com API key.
	"""

	def __init__(self, max_per_second=3):
		self.max_per_second = max_per_second
		self.interval = 1.0 / max_per_second
		self._lock = threading.Lock()
		self._last_call = 0.0

	def acquire(self):
		with self._lock:
			now = time.monotonic()
			wait = self._last_call + self.interval - now
			if wait > 0:
				time.sleep(wait)
			self._last_call = time.monotonic()

	def __enter__(self):
		self.acquire()
		return self

	def __exit__(self, *args):
		pass
