from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging


logger = logging.getLogger(__name__)


class BannerUpdateScheduler:
    def __init__(
        self,
        *,
        update_callback: Callable[[], Awaitable[None]],
        interval_seconds: float,
        cooldown_seconds: float,
    ) -> None:
        self.update_callback = update_callback
        self.interval_seconds = interval_seconds
        self.cooldown_seconds = cooldown_seconds
        self._event = asyncio.Event()
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._update_lock = asyncio.Lock()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            logger.debug("Banner update scheduler is already running.")
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="banner-update-scheduler")
        logger.info("Banner update scheduler started.")

    def request_update(self) -> None:
        self._event.set()

    async def stop(self) -> None:
        self._stop.set()
        self._event.set()
        if self._task is None:
            return
        await self._task
        self._task = None
        logger.info("Banner update scheduler stopped.")

    async def _run(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(self._event.wait(), timeout=self.interval_seconds)
                    self._event.clear()
                    if self._stop.is_set():
                        break
                    await asyncio.sleep(self.cooldown_seconds)
                except TimeoutError:
                    pass

                if self._stop.is_set():
                    break
                await self._safe_update()
        except asyncio.CancelledError:
            logger.info("Banner update scheduler cancelled.")
            raise

    async def _safe_update(self) -> None:
        if self._update_lock.locked():
            logger.debug("Skipping banner update because another update is running.")
            return
        async with self._update_lock:
            try:
                await self.update_callback()
            except Exception:
                logger.exception("Banner update failed.")

