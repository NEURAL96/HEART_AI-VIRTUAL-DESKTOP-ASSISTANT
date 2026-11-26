import re
import time
import socket
import asyncio
import logging
import threading
import ipaddress
import webbrowser
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse, quote
from dataclasses import dataclass, field
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

import httpx

# =============================================================================
# Logging Configuration
# =============================================================================

logger = logging.getLogger("heart.search")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(funcName)s | %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


# =============================================================================
# Configuration & Data Models
# =============================================================================

@dataclass
class HeartConfig:

    serpapi_key: str = "29a8e30e030bdbc94e58390118c68f1e43439a558269c2529834d08ad67f0975"

    # Network & Performance
    connect_timeout: float = 5.0
    read_timeout: float = 10.0
    max_retries: int = 3
    backoff_factor: float = 0.5
    pool_connections: int = 10
    pool_maxsize: int = 20

    # Cache
    cache_max_size: int = 1024
    cache_ttl_seconds: int = 300

    # Security
    max_redirects: int = 3
    allowed_schemes: Tuple[str, ...] = ("http", "https")

    # Search Defaults
    default_num_results: int = 3
    base_url: str = "https://serpapi.com/search"
    maps_base_url: str = "https://www.google.com/maps/dir/"


@dataclass
class SearchResult:
    """Typed model for search results."""
    title: str
    snippet: str
    link: str


@dataclass
class Telemetry:
    """Metrics and telemetry for monitoring."""
    searches: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    errors: int = 0
    total_latency_ms: float = 0.0

    def record_search(self, latency_ms: float, cache_hit: bool):
        self.searches += 1
        self.total_latency_ms += latency_ms
        if cache_hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1

    def record_error(self):
        self.errors += 1

    def get_stats(self) -> Dict[str, Any]:
        avg_lat = self.total_latency_ms / self.searches if self.searches > 0 else 0.0
        return {
            "searches": self.searches,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "errors": self.errors,
            "avg_latency_ms": round(avg_lat, 2)
        }


# =============================================================================
# Async / Sync Bridge (Event Loop Thread)
# =============================================================================

class EventLoopThread:
    """Manages a dedicated background event loop."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._start, daemon=True)
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.thread.start()
        # Wait briefly to ensure the loop is actually running before returning
        time.sleep(0.05)

    def _start(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro):
        """Synchronously wait for an async coroutine to complete."""
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()

    def schedule(self, coro):
        """Schedule a coroutine on the background loop WITHOUT blocking.
        Safe to call from any thread after __init__ completes."""
        return asyncio.run_coroutine_threadsafe(coro, self.loop)


# =============================================================================
# Network Reliability Components
# =============================================================================

class CircuitBreaker:
    """Prevents cascading failures by stopping requests to failing services."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED"
        self._lock = threading.Lock()

    async def call(self, func, *args, **kwargs):
        with self._lock:
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                else:
                    raise ConnectionError("Circuit breaker is OPEN")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e

    def _on_success(self):
        with self._lock:
            self.failure_count = 0
            self.state = "CLOSED"

    def _on_failure(self):
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"


class SecureHTTPClient:
    """Persistent HTTP client with connection pooling and retries."""

    def __init__(self, config: HeartConfig):
        self.config = config
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(config.connect_timeout, read=config.read_timeout),
            limits=httpx.Limits(
                max_connections=config.pool_maxsize,
                max_keepalive_connections=config.pool_connections
            ),
            follow_redirects=False,
            headers={"User-Agent": "HeartAI-SearchEngine/3.0 (Secure; Async)"}
        )
        self.circuit_breaker = CircuitBreaker()

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        retries = 0
        while retries <= self.config.max_retries:
            try:
                return await self.circuit_breaker.call(self.client.request, method, url, **kwargs)
            except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code not in (429, 500, 502, 503, 504):
                    raise

                retries += 1
                if retries > self.config.max_retries:
                    raise

                backoff = self.config.backoff_factor * (2 ** (retries - 1))
                logger.warning(f"Request failed, retrying in {backoff:.2f}s... (Attempt {retries})")
                await asyncio.sleep(backoff)


# =============================================================================
# Security Components
# =============================================================================

class URLValidator:
    """Production-grade URL validator preventing SSRF and unsafe redirects."""
    LOCALHOST_ALIASES = {'localhost', '127.0.0.1', '::1', '0.0.0.0'}
    LOCAL_DOMAIN_PATTERN = re.compile(r'\.local$', re.IGNORECASE)

    def __init__(self, config: HeartConfig):
        self.config = config

    def is_safe_sync(self, url: str) -> bool:
        try:
            if url.startswith(r"\\") or url.startswith("//"): return False
            parsed = urlparse(url)
            if parsed.scheme not in self.config.allowed_schemes: return False
            if not parsed.hostname: return False
            if parsed.hostname.lower() in self.LOCALHOST_ALIASES: return False
            if self.LOCAL_DOMAIN_PATTERN.search(parsed.hostname): return False
            return True
        except Exception:
            return False

    async def _is_internal_ip(self, hostname: str) -> bool:
        """Resolves DNS and checks for private/internal IP ranges."""
        try:
            loop = asyncio.get_running_loop()
            infos = await loop.run_in_executor(
                None,
                lambda: socket.getaddrinfo(hostname, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
            )

            for info in infos:
                ip_str = info[4][0]
                ip_obj = ipaddress.ip_address(ip_str)
                if (ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or
                        ip_obj.is_reserved or ip_obj.is_multicast or ip_obj.is_unspecified):
                    return True
        except socket.gaierror:
            return True  # Fail closed if DNS fails
        return False

    async def validate_redirect_chain(self, client: SecureHTTPClient, url: str) -> Tuple[bool, str]:
        current_url = url
        for _ in range(self.config.max_redirects):
            if not self.is_safe_sync(current_url):
                return False, f"Unsafe URL detected: {current_url}"

            parsed = urlparse(current_url)
            if parsed.hostname and await self._is_internal_ip(parsed.hostname):
                return False, "URL resolves to internal/private IP"

            try:
                resp = await client.request("HEAD", current_url)
                if resp.status_code in (301, 302, 303, 307, 308):
                    next_url = resp.headers.get("location")
                    if not next_url: break
                    next_url = str(httpx.URL(next_url, base_url=current_url))
                    current_url = next_url
                else:
                    break
            except Exception:
                break
        return True, current_url


# =============================================================================
# Caching System
# =============================================================================

class AsyncLRUCache:
    def __init__(self, capacity: int, ttl: int):
        self.capacity = capacity
        self.ttl = ttl
        self.cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self.lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self.lock:
            if key in self.cache:
                value, ts = self.cache[key]
                if time.time() - ts < self.ttl:
                    self.cache.move_to_end(key)
                    return value
                else:
                    del self.cache[key]
            return None

    async def put(self, key: str, value: Any):
        async with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            self.cache[key] = (value, time.time())
            if len(self.cache) > self.capacity:
                self.cache.popitem(last=False)

    async def cleanup(self):
        async with self.lock:
            now = time.time()
            keys_to_delete = [k for k, (_, ts) in self.cache.items() if now - ts >= self.ttl]
            for k in keys_to_delete:
                del self.cache[k]


# =============================================================================
# Search Provider Abstraction
# =============================================================================

class SearchProvider(ABC):
    @abstractmethod
    async def search(self, query: str, num_results: int) -> Tuple[List[SearchResult], Optional[str]]:
        pass


class SerpAPIProvider(SearchProvider):
    def __init__(self, api_key: str, client: SecureHTTPClient, base_url: str):
        self.api_key = api_key
        self.client = client
        self.base_url = base_url

    async def search(self, query: str, num_results: int) -> Tuple[List[SearchResult], Optional[str]]:
        params = {"engine": "google", "q": query, "api_key": self.api_key, "num": num_results}
        try:
            resp = await self.client.request("GET", self.base_url, params=params)
            if resp.status_code == 429:
                return [], "Rate limit exceeded. Please wait before searching again."
            resp.raise_for_status()

            data = resp.json()
            results = []
            for r in data.get("organic_results", []):
                results.append(SearchResult(
                    title=r.get("title", "No Title"),
                    snippet=r.get("snippet", "No description."),
                    link=r.get("link", "")
                ))
            return results, None
        except httpx.HTTPStatusError as e:
            return [], f"HTTP Error: {e.response.status_code}"
        except ValueError:
            return [], "Invalid JSON response received."
        except Exception as e:
            return [], f"Network error: {str(e)}"


# =============================================================================
# Navigation Service
# =============================================================================

class NavigationService:
    def __init__(self, provider: SearchProvider, cache: AsyncLRUCache):
        self.provider = provider
        self.cache = cache

    async def get_navigation_data(self, destination: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        cache_key = f"nav:{destination.lower().strip()}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached[0], cached[1], None

        results, err = await self.provider.search(f"{destination} near me", 1)
        if err: return None, None, err
        if not results: return None, None, f"Could not find '{destination}' nearby."

        place_name = results[0].title
        safe_dest = quote(place_name)
        nav_url = f"https://www.google.com/maps/dir/?api=1&destination={safe_dest}&travelmode=driving"

        await self.cache.put(cache_key, (place_name, nav_url))
        return place_name, nav_url, None


# =============================================================================
# Main Engine
# =============================================================================

class HeartSearchEngine:
    def __init__(self, config: Optional[HeartConfig] = None, provider: Optional[SearchProvider] = None):
        self.config = config or HeartConfig()
        self._runner = EventLoopThread()

        self.http_client = SecureHTTPClient(self.config)
        self.url_validator = URLValidator(self.config)
        self.cache = AsyncLRUCache(self.config.cache_max_size, self.config.cache_ttl_seconds)
        self.telemetry = Telemetry()

        if provider:
            self.provider = provider
        else:
            self.provider = SerpAPIProvider(self.config.serpapi_key, self.http_client, self.config.base_url)

        self.nav_service = NavigationService(self.provider, self.cache)

        self.last_results: List[Dict[str, str]] = []
        self._results_lock = threading.Lock()

        # ✅ FIXED: Use run_coroutine_threadsafe instead of direct loop.create_task()
        # This is safe to call from ANY thread, including during module import,
        # because it submits through the thread-safe Future mechanism rather than
        # touching the loop object directly from the wrong thread.
        self._runner.schedule(self._background_worker())

        if not self.config.serpapi_key:
            logger.warning("SERPAPI_KEY is missing. Search functionality will be limited.")

    async def _background_worker(self):
        while True:
            await asyncio.sleep(60)
            await self.cache.cleanup()
            logger.debug(f"Telemetry Stats: {self.telemetry.get_stats()}")

    def get_telemetry(self) -> Dict[str, Any]:
        return self.telemetry.get_stats()

    # Synchronous Wrappers
    def search_web(self, query: str, num_results: int = 3) -> str:
        return self._runner.run(self.async_search_web(query, num_results))

    def open_result(self, index: int) -> str:
        return self._runner.run(self.async_open_result(index))

    def navigate_to(self, destination: str) -> str:
        return self._runner.run(self.async_navigate_to(destination))

    # Unified Handler for Web Intelligence Tool
    def handle_web_request(self, action: str, query: str = "", result_index: int = 0) -> str:
        action = action.lower().strip()
        if action == "search":
            return self.search_web(query)
        elif action == "open":
            return self.open_result(result_index)
        elif action == "navigate":
            return self.navigate_to(query)
        else:
            return f" Unknown action '{action}'. Use: search, open, or navigate."

    # Asynchronous Core
    async def async_search_web(self, query: str, num_results: int = 3) -> str:
        start_time = time.time()
        if not self.config.serpapi_key:
            self.telemetry.record_error()
            return " Search engine unavailable (Missing SERPAPI_KEY)."

        cache_key = f"search:{query.lower().strip()}:{num_results}"
        cached_data = await self.cache.get(cache_key)

        if cached_data:
            self.telemetry.record_search((time.time() - start_time) * 1000, cache_hit=True)
            return self._format_results(cached_data, query, from_cache=True)

        results, error = await self.provider.search(query, num_results)

        if error:
            self.telemetry.record_error()
            return f" Search failed: {error}"

        if not results:
            self.telemetry.record_search((time.time() - start_time) * 1000, cache_hit=False)
            return f"No real-time results found for '{query}'."

        unique_results = []
        seen_urls = set()
        for r in results:
            if r.link not in seen_urls and self.url_validator.is_safe_sync(r.link):
                score = 10 if r.link.startswith("https://") else 0
                if any(d in r.link for d in ["wikipedia.org", "github.com", "stackoverflow.com"]):
                    score += 5
                unique_results.append((score, r))
                seen_urls.add(r.link)

        unique_results.sort(key=lambda x: x[0], reverse=True)
        final_results = [r[1] for r in unique_results]

        await self.cache.put(cache_key, final_results)
        self.telemetry.record_search((time.time() - start_time) * 1000, cache_hit=False)

        return self._format_results(final_results, query)

    def _format_results(self, results: List[SearchResult], query: str, from_cache: bool = False) -> str:
        with self._results_lock:
            self.last_results = []

        prefix = "⚡ **Cached Intelligence Report" if from_cache else "**Real-Time Intelligence Report"
        report = f"{prefix}: '{query}'**\n\n"

        valid_count = 0
        for i, res in enumerate(results[:self.config.default_num_results]):
            if self.url_validator.is_safe_sync(res.link):
                with self._results_lock:
                    self.last_results.append({'title': res.title, 'link': res.link})

                report += f"**{valid_count + 1}. {res.title}**\n• {res.snippet}\n Link saved (Say 'Open result {valid_count + 1}' to view).\n\n"
                valid_count += 1
            else:
                report += f"**{i + 1}. {res.title}**\n• {res.snippet}\n Link blocked for security.\n\n"

        if valid_count == 0 and results:
            report += " No safe links were found in the results."

        return report

    async def async_open_result(self, index: int) -> str:
        with self._results_lock:
            results_copy = list(self.last_results)

        if 1 <= index <= len(results_copy):
            target = results_copy[index - 1]
            is_safe, final_url = await self.url_validator.validate_redirect_chain(self.http_client, target['link'])

            if is_safe:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(self._runner.executor, webbrowser.open, final_url)
                return f" Opening: {target['title']}"
            else:
                logger.warning(f"Blocked unsafe redirect/URL: {final_url}")
                return " Security Alert: This link was blocked."
        else:
            return f" Invalid result number. Please search again."

    async def async_navigate_to(self, destination: str) -> str:
        if not self.config.serpapi_key:
            return " Navigation unavailable (Missing SERPAPI_KEY)."

        place_name, nav_url, error = await self.nav_service.get_navigation_data(destination)

        if error:
            return f" Navigation lookup failed: {error}"

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._runner.executor, webbrowser.open, nav_url)

        return f" **Navigating to: {place_name}**\n• Opening Google Maps with the best route..."


# =============================================================================
# Global Instance
# =============================================================================

search_agent = HeartSearchEngine()