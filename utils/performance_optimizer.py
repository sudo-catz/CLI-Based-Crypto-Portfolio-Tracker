# -*- coding: utf-8 -*-
"""
Performance Optimization Module (Cache-Free)
------------------------------------------
Provides connection pooling, request batching, and enhanced concurrent processing
without any caching functionality to ensure maximum data freshness.

Key Features:
- HTTP connection pooling for reduced latency
- Request batching for API efficiency
- Enhanced error handling with exponential backoff
- Performance metrics and monitoring (no cache stats)
- Memory-efficient data processing
"""

import asyncio
import time
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, TypeVar, Tuple
from collections import defaultdict
import aiohttp
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
from dataclasses import dataclass, asdict
from functools import wraps

# Import configuration and utilities
from config.constants import *
from utils.helpers import print_info, print_warning, print_error, print_success

T = TypeVar("T")


@dataclass
class PerformanceMetrics:
    """Tracks performance metrics for optimization analysis (no cache metrics)."""

    total_requests: int = 0
    total_time: float = 0.0
    average_response_time: float = 0.0
    error_count: int = 0
    concurrent_tasks_peak: int = 0


class ConnectionPoolManager:
    """HTTP connection pooling for improved performance."""

    def __init__(self, pool_connections: int = 20, pool_maxsize: int = 20):
        self.pool_connections = pool_connections
        self.pool_maxsize = pool_maxsize
        self._session = None
        self._connector = None

    def get_requests_session(self) -> requests.Session:
        """Get a requests session with connection pooling."""
        if self._session is None:
            self._session = requests.Session()

            # Configure retry strategy
            retry_strategy = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
            )

            adapter = HTTPAdapter(
                pool_connections=self.pool_connections,
                pool_maxsize=self.pool_maxsize,
                max_retries=retry_strategy,
            )

            self._session.mount("http://", adapter)
            self._session.mount("https://", adapter)

        return self._session

    async def get_aiohttp_connector(self) -> aiohttp.TCPConnector:
        """Get an aiohttp connector with connection pooling."""
        if self._connector is None:
            self._connector = aiohttp.TCPConnector(
                limit=self.pool_connections,
                limit_per_host=self.pool_maxsize,
                ttl_dns_cache=300,
                use_dns_cache=True,
            )

        return self._connector

    async def close(self):
        """Clean up connections."""
        if self._session:
            self._session.close()
        if self._connector:
            await self._connector.close()


class BatchRequestProcessor:
    """Batch processing for API requests."""

    def __init__(self, batch_size: int = 5, batch_delay: float = 0.1):
        self.batch_size = batch_size
        self.batch_delay = batch_delay
        self._batches: Dict[str, List[Callable]] = defaultdict(list)

    async def add_to_batch(self, batch_key: str, request_func: Callable) -> Any:
        """Add request to batch for processing."""
        self._batches[batch_key].append(request_func)

        if len(self._batches[batch_key]) >= self.batch_size:
            batch = self._batches[batch_key].copy()
            self._batches[batch_key].clear()
            return await self._execute_batch(batch)

        return None

    async def _execute_batch(self, batch: List[Callable]) -> List[Any]:
        """Execute a batch of requests concurrently."""
        tasks = []
        for request_func in batch:
            if asyncio.iscoroutinefunction(request_func):
                tasks.append(request_func())
            else:
                loop = asyncio.get_event_loop()
                tasks.append(loop.run_in_executor(None, request_func))

        await asyncio.sleep(self.batch_delay)
        return await asyncio.gather(*tasks, return_exceptions=True)


class PerformanceOptimizer:
    """Main performance optimization manager (cache-free)."""

    def __init__(self):
        self.connection_manager = ConnectionPoolManager()
        self.batch_processor = BatchRequestProcessor()
        self.metrics = PerformanceMetrics()
        self._start_time = None
        self._active_tasks = 0

        # Setup logging
        self.logger = logging.getLogger(__name__)

    def cached(self, ttl: Optional[int] = None, key_prefix: str = "default"):
        """Decorator that bypasses caching - always executes function for fresh data."""

        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @wraps(func)
            async def async_wrapper(*args, **kwargs) -> T:
                # Always execute function - no caching
                start_time = time.time()

                try:
                    if asyncio.iscoroutinefunction(func):
                        result = await func(*args, **kwargs)
                    else:
                        result = func(*args, **kwargs)

                    # Update metrics
                    self.metrics.total_requests += 1
                    self.metrics.total_time += time.time() - start_time

                    return result
                except Exception as e:
                    self.metrics.error_count += 1
                    raise

            @wraps(func)
            def sync_wrapper(*args, **kwargs) -> T:
                # Always execute function - no caching
                start_time = time.time()

                try:
                    result = func(*args, **kwargs)

                    self.metrics.total_requests += 1
                    self.metrics.total_time += time.time() - start_time

                    return result
                except Exception as e:
                    self.metrics.error_count += 1
                    raise

            return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

        return decorator

    async def optimized_gather(self, tasks: List[Callable], max_concurrent: int = 10) -> List[Any]:
        """Execute tasks with controlled concurrency and optimized gathering."""
        semaphore = asyncio.Semaphore(max_concurrent)
        self._active_tasks = len(tasks)
        self.metrics.concurrent_tasks_peak = max(
            self.metrics.concurrent_tasks_peak, self._active_tasks
        )

        async def controlled_task(task_func):
            async with semaphore:
                try:
                    if asyncio.iscoroutinefunction(task_func):
                        return await task_func()
                    else:
                        loop = asyncio.get_event_loop()
                        return await loop.run_in_executor(None, task_func)
                except Exception as e:
                    self.logger.error(f"Task failed: {e}")
                    return e

        # Execute all tasks with controlled concurrency
        results = await asyncio.gather(
            *[controlled_task(task) for task in tasks], return_exceptions=True
        )

        self._active_tasks = 0
        return results

    def start_analysis(self):
        """Mark the start of portfolio analysis."""
        self._start_time = time.time()
        self.metrics = PerformanceMetrics()  # Reset metrics
        print_info("⚡ Performance mode enabled - faster analysis without caching")

    def end_analysis(self):
        """Mark the end of analysis and print performance report."""
        if self._start_time:
            total_time = time.time() - self._start_time
            self.metrics.average_response_time = (
                self.metrics.total_time / self.metrics.total_requests
                if self.metrics.total_requests > 0
                else 0.0
            )

            print_info("=" * 50)
            print_success("📊 Performance Analysis Report (Cache-Free)")
            print_info(f"   Total Analysis Time: {total_time:.1f}s")
            print_info(f"   Mode: Real-time (no caching)")
            print_info(f"   Total Requests: {self.metrics.total_requests}")
            print_info(f"   Average Response Time: {self.metrics.average_response_time:.2f}s")
            print_info(f"   Peak Concurrent Tasks: {self.metrics.concurrent_tasks_peak}")
            print_info(f"   Error Count: {self.metrics.error_count}")

            # Performance recommendations
            if self.metrics.average_response_time > 2.0:
                print_warning("   💡 High response times - check network conditions")
            if self.metrics.error_count > 0:
                print_warning(f"   ⚠️  {self.metrics.error_count} errors occurred - check logs")

            print_info("=" * 50)

    async def cleanup(self):
        """Cleanup resources."""
        await self.connection_manager.close()
        print_info("🧹 Performance optimizer cleanup complete")


# Global instance - no caching
performance_optimizer = PerformanceOptimizer()


def enable_performance_mode():
    """Enable performance optimization mode."""
    performance_optimizer.start_analysis()


def disable_performance_mode():
    """Disable performance optimization mode."""
    performance_optimizer.end_analysis()


async def cleanup_performance_mode():
    """Cleanup performance optimization resources."""
    performance_optimizer.end_analysis()
    await performance_optimizer.cleanup()


# Convenience decorators - now cache-free
def cached_api_call(ttl: int = 180):
    """Decorator for API calls - no caching, always fresh data."""
    return performance_optimizer.cached(ttl=ttl, key_prefix="api")


def cached_price_data(ttl: int = 300):
    """Decorator for price data - no caching, always fresh data."""
    return performance_optimizer.cached(ttl=ttl, key_prefix="price")


def cached_wallet_data(ttl: int = 300):
    """Decorator for wallet data - no caching, always fresh data."""
    return performance_optimizer.cached(ttl=ttl, key_prefix="wallet")
