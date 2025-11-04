class WebSocketConnectionError(Exception):
    """WebSocket connection failed or was lost.

    Raised when:
    - Initial WebSocket connection fails
    - Connection is unexpectedly closed
    - Network errors during communication
    - Invalid API key or authentication failure
    """


class AudioFormatError(Exception):
    """Invalid audio format or parameters.

    Raised when:
    - Audio data is not bytes type
    - PCM16 data has odd byte length
    - Sample rate is not 24000 Hz
    - Audio format is not PCM16
    - Audio data fails validation checks
    """


class SessionInitializationError(Exception):
    """Session initialization or configuration failed.

    Raised when:
    - WebSocket session creation fails
    - Invalid model specified
    - Unsupported voice parameter
    - Session update fails
    - Configuration parameters invalid
    """
