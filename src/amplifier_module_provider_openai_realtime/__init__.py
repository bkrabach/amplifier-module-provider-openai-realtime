"""OpenAI Realtime API provider module for Amplifier."""

__version__ = "0.1.0"


def mount():
    """Entry point for Amplifier module loading.

    Returns the provider class that implements the provider contract.
    """
    from .provider import OpenAIRealtimeProvider

    return OpenAIRealtimeProvider
