import base64

import numpy as np

from .exceptions import AudioFormatError


def encode_pcm16(audio_array: np.ndarray) -> bytes:
    """Encode numpy array to PCM16 bytes.

    Args:
        audio_array: np.ndarray with dtype=np.int16

    Returns:
        bytes: PCM16 audio data (little-endian)

    Raises:
        AudioFormatError: If array is not int16 dtype
    """
    if audio_array.dtype != np.int16:
        raise AudioFormatError(f"Expected int16 array, got {audio_array.dtype}")
    return audio_array.tobytes(order="C")


def decode_pcm16(audio_bytes: bytes) -> np.ndarray:
    """Decode PCM16 bytes to numpy array.

    Args:
        audio_bytes: PCM16 audio data

    Returns:
        np.ndarray: Audio array with dtype=np.int16

    Raises:
        AudioFormatError: If byte length not multiple of 2
    """
    if len(audio_bytes) % 2 != 0:
        raise AudioFormatError("Invalid PCM16 data (odd byte length)")
    return np.frombuffer(audio_bytes, dtype=np.int16)


def validate_audio_format(audio_data: bytes, expected_sample_rate: int = 24000) -> bool:
    """Validate audio format.

    Args:
        audio_data: Audio bytes
        expected_sample_rate: Required sample rate

    Returns:
        bool: True if valid

    Raises:
        AudioFormatError: If validation fails with reason
    """
    if not isinstance(audio_data, bytes):
        raise AudioFormatError("Audio data must be bytes")
    if len(audio_data) % 2 != 0:
        raise AudioFormatError("Invalid PCM16 data (odd byte length)")
    return True


def encode_base64_audio(audio_bytes: bytes) -> str:
    """Encode PCM16 to base64 for WebSocket transmission.

    Args:
        audio_bytes: PCM16 audio data

    Returns:
        str: Base64-encoded audio
    """
    return base64.b64encode(audio_bytes).decode("ascii")


def decode_base64_audio(base64_str: str) -> bytes:
    """Decode base64 audio from WebSocket.

    Args:
        base64_str: Base64-encoded audio string

    Returns:
        bytes: PCM16 audio data
    """
    return base64.b64decode(base64_str)
