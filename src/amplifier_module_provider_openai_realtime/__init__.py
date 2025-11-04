"""OpenAI Realtime API provider module for Amplifier."""

import os
from collections.abc import Awaitable
from collections.abc import Callable
from typing import Any

__version__ = "0.1.0"


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> Callable[[], Awaitable[None]]:
    """
    Mount the provider module.

    Args:
        coordinator: Amplifier module coordinator
        config: Provider configuration

    Returns:
        Async cleanup function

    Raises:
        ValueError: If API key not provided
    """
    from .provider import OpenAIRealtimeProvider

    config = config or {}

    # Extract configuration
    api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OpenAI API key required (config.api_key or $OPENAI_API_KEY)")

    # Initialize provider
    provider = OpenAIRealtimeProvider(api_key=api_key, config=config, coordinator=coordinator)

    # Mount to coordinator
    await coordinator.mount("providers", provider, name="openai-realtime")

    # Return cleanup function
    async def cleanup():
        await provider.session_manager.cleanup()

    return cleanup
