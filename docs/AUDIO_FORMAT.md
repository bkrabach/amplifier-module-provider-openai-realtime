# Audio Format

This document specifies the audio encoding/decoding requirements for the OpenAI Realtime provider.

## Overview

The provider uses **PCM16** (Pulse Code Modulation, 16-bit) format at **24kHz** sample rate for all audio I/O. This is OpenAI's native format for the Realtime API, ensuring maximum quality with minimal overhead.

## Audio Specifications

### Input Format (to Provider)

| Parameter       | Value           | Description                          |
|-----------------|-----------------|--------------------------------------|
| **Encoding**    | PCM16           | 16-bit signed integer, linear PCM    |
| **Sample Rate** | 24,000 Hz       | 24kHz (OpenAI Realtime requirement)  |
| **Channels**    | 1 (mono)        | Single audio channel                 |
| **Byte Order**  | Little-endian   | Least significant byte first         |
| **Sample Size** | 2 bytes         | 16 bits per sample                   |

### Output Format (from Provider)

**Identical to input format** - no conversion occurs.

The provider returns audio in the same PCM16, 24kHz, mono format that OpenAI provides.

## Technical Details

### PCM16 Encoding

**What is PCM16?**

PCM16 represents audio samples as 16-bit signed integers ranging from -32,768 to +32,767:

```
Waveform:     -1.0    0.0   +1.0
              ↓       ↓      ↓
PCM16:     -32768    0   +32767
```

**Characteristics:**
- Uncompressed (no lossy codec artifacts)
- Linear representation (simple encoding/decoding)
- Deterministic (same input always produces same output)
- Widely supported (standard audio format)

### Sample Rate: 24kHz

**Why 24kHz?**

OpenAI's Realtime API requires 24kHz sampling rate specifically:

- **Nyquist frequency**: 12kHz (captures frequencies up to 12kHz)
- **Human speech**: 80Hz - 14kHz (well within 12kHz limit)
- **Bandwidth efficiency**: Half the data of 48kHz with full speech fidelity
- **Optimized for voice**: Not music production, but perfect for conversation

**Comparison**:
| Rate | Use Case | Bandwidth |
|------|----------|-----------|
| 8kHz | Telephone quality | 4kHz max |
| 16kHz | Wideband speech | 8kHz max |
| **24kHz** | **Realtime speech** | **12kHz max** |
| 44.1kHz | CD audio | 22.05kHz max |
| 48kHz | Professional audio | 24kHz max |

### Bit Depth: 16-bit

**Why 16-bit?**

- **Dynamic range**: 96dB (sufficient for speech)
- **Signal-to-noise ratio**: ~96dB (inaudible noise floor for voice)
- **File size balance**: Compact without quality loss for speech
- **Standard format**: Wide compatibility across audio tools

**Comparison**:
| Bit Depth | Dynamic Range | Use Case |
|-----------|---------------|----------|
| 8-bit | 48dB | Low quality, legacy |
| **16-bit** | **96dB** | **Standard quality** |
| 24-bit | 144dB | Professional recording |

### Mono (Single Channel)

**Why mono?**

- Voice conversations are typically mono
- Reduces bandwidth by 50% vs stereo
- Simplifies processing (no channel mixing)
- OpenAI Realtime API requirement

## Data Structures

### Message Format (Input)

When sending audio to the provider:

```python
{
    "role": "user",
    "content": [
        {
            "type": "audio",
            "data": bytes,         # PCM16 audio data
            "format": "pcm16",     # Format specification
            "sample_rate": 24000   # Sample rate in Hz
        }
    ]
}
```

**Field descriptions**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | str | Yes | Must be `"audio"` |
| `data` | bytes | Yes | Raw PCM16 audio bytes |
| `format` | str | No | `"pcm16"` (assumed if omitted) |
| `sample_rate` | int | No | 24000 (assumed if omitted) |

### Response Format (Output)

Audio returned in `ProviderResponse.raw` field:

```python
{
    "audio_data": bytes,         # PCM16 audio bytes
    "audio_format": "pcm16",     # Format specification
    "sample_rate": 24000,        # Sample rate in Hz
    "transcript": str,           # Text version
    "session_id": str,           # WebSocket session ID
    "websocket_response": dict   # Full OpenAI response
}
```

## Encoding/Decoding

### Python: NumPy Arrays ↔ PCM16

The provider includes `audio_codec.py` utilities for encoding/decoding:

```python
import numpy as np
from amplifier_module_provider_openai_realtime.audio_codec import (
    encode_pcm16,
    decode_pcm16,
    validate_audio_format
)

# NumPy array → PCM16 bytes
audio_array = np.array([0, 16384, -16384, 0], dtype=np.int16)
audio_bytes = encode_pcm16(audio_array)
# → b'\x00\x00\x00@\x00\xC0\x00\x00'

# PCM16 bytes → NumPy array
audio_array = decode_pcm16(audio_bytes)
# → array([0, 16384, -16384, 0], dtype=int16)

# Validate format
is_valid = validate_audio_format(audio_bytes, expected_sample_rate=24000)
```

**Key functions**:

```python
def encode_pcm16(audio_array: np.ndarray) -> bytes:
    """
    Encode numpy array to PCM16 bytes.

    Args:
        audio_array: np.ndarray with dtype=np.int16

    Returns:
        bytes: PCM16 audio data (little-endian)

    Raises:
        ValueError: If array is not int16 dtype
    """

def decode_pcm16(audio_bytes: bytes) -> np.ndarray:
    """
    Decode PCM16 bytes to numpy array.

    Args:
        audio_bytes: PCM16 audio data

    Returns:
        np.ndarray: Audio array with dtype=np.int16

    Raises:
        ValueError: If byte length not multiple of 2
    """

def validate_audio_format(
    audio_data: bytes,
    expected_sample_rate: int = 24000
) -> bool:
    """
    Validate audio format and sample rate.

    Args:
        audio_data: Audio bytes to validate
        expected_sample_rate: Required sample rate (default 24000)

    Returns:
        bool: True if valid PCM16 format

    Raises:
        AudioFormatError: If validation fails with reason
    """
```

### File I/O: WAV Format

To save/load PCM16 audio as WAV files:

```python
import wave
import numpy as np

# Save PCM16 bytes as WAV file
def save_wav(audio_bytes: bytes, filepath: str, sample_rate: int = 24000):
    """Save PCM16 audio to WAV file."""
    with wave.open(filepath, 'wb') as wav_file:
        wav_file.setnchannels(1)           # Mono
        wav_file.setsampwidth(2)           # 16-bit (2 bytes)
        wav_file.setframerate(sample_rate) # 24kHz
        wav_file.writeframes(audio_bytes)

# Load WAV file as PCM16 bytes
def load_wav(filepath: str) -> tuple[bytes, int]:
    """Load WAV file as PCM16 audio."""
    with wave.open(filepath, 'rb') as wav_file:
        if wav_file.getnchannels() != 1:
            raise ValueError("Only mono audio supported")
        if wav_file.getsampwidth() != 2:
            raise ValueError("Only 16-bit audio supported")

        sample_rate = wav_file.getframerate()
        audio_bytes = wav_file.readframes(wav_file.getnframes())

        return audio_bytes, sample_rate
```

**Example usage**:

```python
# Save response audio
audio_output = response.raw["audio_data"]
save_wav(audio_output, "response.wav")

# Load audio for sending
audio_input, rate = load_wav("input.wav")
if rate != 24000:
    raise ValueError(f"Expected 24kHz, got {rate}Hz")

# Send to provider
response = await session.execute({
    "role": "user",
    "content": [{"type": "audio", "data": audio_input}]
})
```

## Conversion Examples

### Example 1: Record Audio (PyAudio)

```python
import pyaudio
import numpy as np

def record_audio(duration: float) -> bytes:
    """Record audio from microphone (24kHz PCM16)."""
    p = pyaudio.PyAudio()

    stream = p.open(
        format=pyaudio.paInt16,     # 16-bit
        channels=1,                 # Mono
        rate=24000,                 # 24kHz
        input=True,
        frames_per_buffer=1024
    )

    frames = []
    for _ in range(0, int(24000 / 1024 * duration)):
        data = stream.read(1024)
        frames.append(data)

    stream.stop_stream()
    stream.close()
    p.terminate()

    return b''.join(frames)

# Record 3 seconds
audio_input = record_audio(3.0)

# Send to provider
response = await session.execute({
    "role": "user",
    "content": [{"type": "audio", "data": audio_input}]
})
```

### Example 2: Play Audio (PyAudio)

```python
def play_audio(audio_bytes: bytes):
    """Play PCM16 audio through speakers."""
    p = pyaudio.PyAudio()

    stream = p.open(
        format=pyaudio.paInt16,     # 16-bit
        channels=1,                 # Mono
        rate=24000,                 # 24kHz
        output=True
    )

    stream.write(audio_bytes)

    stream.stop_stream()
    stream.close()
    p.terminate()

# Get audio from response
audio_output = response.raw["audio_data"]

# Play through speakers
play_audio(audio_output)
```

### Example 3: Resample Audio (librosa)

If you have audio at different sample rate:

```python
import librosa
import numpy as np

def resample_to_24khz(audio_bytes: bytes, original_rate: int) -> bytes:
    """Resample audio to 24kHz."""
    # Decode to array
    audio_array = np.frombuffer(audio_bytes, dtype=np.int16)

    # Convert to float for resampling
    audio_float = audio_array.astype(np.float32) / 32768.0

    # Resample
    audio_resampled = librosa.resample(
        audio_float,
        orig_sr=original_rate,
        target_sr=24000
    )

    # Convert back to int16
    audio_int16 = (audio_resampled * 32768.0).astype(np.int16)

    # Encode to bytes
    return audio_int16.tobytes()

# Example: Convert 48kHz audio to 24kHz
audio_48khz, rate = load_wav("input_48khz.wav")
audio_24khz = resample_to_24khz(audio_48khz, 48000)

# Now ready to send
response = await session.execute({
    "role": "user",
    "content": [{"type": "audio", "data": audio_24khz}]
})
```

## Validation

The provider validates audio format automatically:

```python
class AudioFormatError(Exception):
    """Audio format validation failed."""

# Validation checks:
# 1. Audio data is bytes
# 2. Byte length is multiple of 2 (16-bit samples)
# 3. Sample rate is 24000 (if specified)
# 4. Format is "pcm16" (if specified)
```

**Example validation errors**:

```python
# Wrong type
{"type": "audio", "data": "not bytes"}
# → AudioFormatError: Audio data must be bytes

# Odd byte length
{"type": "audio", "data": b"\x00\x00\x00"}
# → AudioFormatError: Invalid PCM16 data (odd byte length)

# Wrong sample rate
{"type": "audio", "data": audio, "sample_rate": 48000}
# → AudioFormatError: Expected 24000Hz, got 48000Hz

# Wrong format
{"type": "audio", "data": audio, "format": "mp3"}
# → AudioFormatError: Expected pcm16 format, got mp3
```

## Size Calculations

### Duration ↔ Byte Size

```python
# Calculate byte size from duration
def duration_to_bytes(seconds: float, sample_rate: int = 24000) -> int:
    """Calculate byte size for audio duration."""
    samples = int(seconds * sample_rate)
    return samples * 2  # 2 bytes per sample

# Calculate duration from byte size
def bytes_to_duration(byte_size: int, sample_rate: int = 24000) -> float:
    """Calculate audio duration from byte size."""
    samples = byte_size // 2  # 2 bytes per sample
    return samples / sample_rate

# Examples:
duration_to_bytes(1.0)    # → 48,000 bytes (1 second)
duration_to_bytes(3.0)    # → 144,000 bytes (3 seconds)
bytes_to_duration(48000)  # → 1.0 seconds
```

### Network Bandwidth

```python
# Bandwidth for PCM16 @ 24kHz
sample_rate = 24000  # samples/second
sample_size = 2      # bytes/sample
channels = 1         # mono

bandwidth = sample_rate * sample_size * channels
# = 48,000 bytes/second
# = 48 KB/s
# = 384 kbps

# One minute of audio
minute_size = bandwidth * 60
# = 2,880,000 bytes
# = 2.88 MB
```

## Troubleshooting

### Issue: "Invalid PCM16 data (odd byte length)"

**Cause**: Audio data has odd number of bytes (16-bit samples require even bytes).

**Solution**: Ensure audio data length is multiple of 2:

```python
if len(audio_bytes) % 2 != 0:
    # Pad with zero byte
    audio_bytes += b'\x00'
```

### Issue: "Expected 24000Hz, got XXXXHz"

**Cause**: Audio recorded/loaded at wrong sample rate.

**Solution**: Resample to 24kHz:

```python
audio_24khz = resample_to_24khz(audio_bytes, original_rate)
```

### Issue: Audio sounds distorted

**Cause**: Clipping (samples exceed ±32767 range).

**Solution**: Normalize audio before encoding:

```python
def normalize_audio(audio_array: np.ndarray) -> np.ndarray:
    """Normalize audio to prevent clipping."""
    max_val = np.abs(audio_array).max()
    if max_val > 32767:
        audio_array = (audio_array * 32767 / max_val).astype(np.int16)
    return audio_array
```

### Issue: Audio too quiet

**Cause**: Low recording levels.

**Solution**: Amplify audio before encoding:

```python
def amplify_audio(audio_array: np.ndarray, gain_db: float) -> np.ndarray:
    """Amplify audio by gain (in dB)."""
    gain_linear = 10 ** (gain_db / 20)
    audio_amplified = (audio_array * gain_linear).astype(np.int16)
    return np.clip(audio_amplified, -32768, 32767)
```

## Performance Considerations

### Memory Usage

```python
# 1 minute of PCM16 @ 24kHz:
# 24000 samples/sec * 60 sec * 2 bytes = 2.88 MB

# 10 minute conversation:
# ~29 MB in memory

# Best practice: Stream audio instead of buffering
```

### CPU Usage

```python
# Encoding/decoding is minimal:
# - PCM16 → bytes: Simple cast, ~1ms for 1 minute
# - bytes → PCM16: Simple cast, ~1ms for 1 minute

# No complex codec overhead like MP3/Opus
```

### Network Usage

```python
# 384 kbps = 48 KB/s
# Typical conversation (15 seconds speaking per minute):
# = 48 KB/s * 15s = 720 KB/minute

# Acceptable for most network connections
```

## See Also

- [Architecture](ARCHITECTURE.md) - Module design overview
- [Session Lifecycle](SESSION_LIFECYCLE.md) - WebSocket management
- [API Contract](API_CONTRACT.md) - Provider protocol details
- [Examples](EXAMPLES.md) - Usage recipes
