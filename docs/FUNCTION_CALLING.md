# Function Calling

This document describes how the OpenAI Realtime provider integrates with Amplifier's tool system.

## Overview

The provider supports **full function calling** through OpenAI's Realtime API. Voice input can trigger tool calls, which execute through Amplifier's standard tool mechanism. The model continues with voice output after receiving tool results.

**Key principle**: Tools work identically to text-based providers - no special audio handling required.

## Flow Diagram

```
User speaks
    ↓
Audio sent to OpenAI
    ↓
Model analyzes and decides: Tool call needed
    ↓
Provider parses tool call from response
    ↓
Amplifier executes tool (standard mechanism)
    ↓
Tool result sent back via WebSocket
    ↓
Model generates audio response with result
    ↓
Audio played to user
```

## Tool Configuration

### Basic Setup

Tools are configured identically to text providers:

```python
config = {
    "session": {
        "orchestrator": "loop-basic",
        "context": "context-simple"
    },
    "providers": [{
        "module": "provider-openai-realtime",
        "source": "git+https://github.com/robotdad/amplifier-module-provider-openai-realtime@main",
        "config": {
            "api_key": "${OPENAI_API_KEY}",
            "model": "gpt-4o-realtime-preview-2024-12-17",
            "voice": "alloy"
        }
    }],
    "tools": [
        {
            "module": "tool-filesystem",
            "source": "git+https://github.com/microsoft/amplifier-module-tool-filesystem@main"
        },
        {
            "module": "tool-web",
            "source": "git+https://github.com/microsoft/amplifier-module-tool-web@main"
        }
    ]
}

async with AmplifierSession(config=config) as session:
    # Voice input can trigger any configured tool
    response = await session.execute({
        "role": "user",
        "content": [{"type": "audio", "data": audio_input}]
    })
```

**Result**: Model can call `tool-filesystem` or `tool-web` based on voice input.

### Tool Definitions

Tools automatically register their schemas with the provider:

```python
# Tool module defines schema
class WebTool:
    name = "web_search"
    description = "Search the web for information"

    schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return",
                "default": 5
            }
        },
        "required": ["query"]
    }

    async def execute(self, query: str, max_results: int = 5):
        # ... implementation
```

**Provider sends to OpenAI**:
```json
{
    "type": "session.update",
    "session": {
        "tools": [
            {
                "type": "function",
                "name": "web_search",
                "description": "Search the web for information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "max_results": {"type": "integer", "description": "Maximum results", "default": 5}
                    },
                    "required": ["query"]
                }
            }
        ]
    }
}
```

## Tool Call Protocol

### Detection Phase

**User speaks**: "What's the weather in San Francisco?"

**OpenAI response**:
```json
{
    "type": "response.function_call_arguments.done",
    "call_id": "call_abc123",
    "name": "get_weather",
    "arguments": "{\"location\":\"San Francisco\"}"
}
```

**Provider parses**:
```python
def parse_tool_calls(self, response: ProviderResponse) -> list[ToolCall]:
    """Extract tool calls from response."""
    if not response.raw.get("websocket_response"):
        return []

    ws_response = response.raw["websocket_response"]

    if ws_response.get("type") == "response.function_call_arguments.done":
        return [
            ToolCall(
                tool=ws_response["name"],
                arguments=json.loads(ws_response["arguments"]),
                id=ws_response["call_id"]
            )
        ]

    return []
```

### Execution Phase

**Amplifier orchestrator executes tool**:
```python
# Standard Amplifier tool execution
tool_result = await tool_manager.execute(
    tool_name="get_weather",
    arguments={"location": "San Francisco"}
)

# Result: {"temperature": 72, "condition": "sunny"}
```

### Result Submission

**Provider sends back to OpenAI**:
```python
await self.websocket.send({
    "type": "conversation.item.create",
    "item": {
        "type": "function_call_output",
        "call_id": "call_abc123",
        "output": json.dumps({
            "temperature": 72,
            "condition": "sunny"
        })
    }
})

await self.websocket.send({
    "type": "response.create"
})
```

### Response Phase

**OpenAI generates audio with result**:
```json
{
    "type": "response.audio.done",
    "audio": "base64_encoded_audio",
    "transcript": "It's currently 72 degrees and sunny in San Francisco."
}
```

**Provider returns to app**:
```python
ProviderResponse(
    content="It's currently 72 degrees and sunny in San Francisco.",
    raw={
        "audio_data": decoded_audio_bytes,
        "transcript": "It's currently 72 degrees and sunny in San Francisco.",
        # ...
    }
)
```

## Complete Example

### Weather Assistant

```python
from amplifier_core import AmplifierSession
from pathlib import Path

# Configuration with tool
config = {
    "session": {
        "orchestrator": "loop-basic",
        "context": "context-simple"
    },
    "providers": [{
        "module": "provider-openai-realtime",
        "source": "git+https://github.com/robotdad/amplifier-module-provider-openai-realtime@main",
        "config": {
            "api_key": "${OPENAI_API_KEY}",
            "model": "gpt-4o-realtime-preview-2024-12-17",
            "voice": "alloy"
        }
    }],
    "tools": [{
        "module": "tool-weather",
        "source": "git+https://github.com/example/amplifier-module-tool-weather@main",
        "config": {
            "api_key": "${WEATHER_API_KEY}"
        }
    }]
}

async def voice_weather_assistant():
    """Voice assistant that can check weather."""

    async with AmplifierSession(config=config) as session:
        # User asks about weather
        audio_input = record_audio()  # "What's the weather in Tokyo?"

        response = await session.execute({
            "role": "user",
            "content": [{"type": "audio", "data": audio_input}]
        })

        # Model calls weather tool automatically
        # Tool executes
        # Model speaks result with audio

        audio_output = response.raw["audio_data"]
        play_audio(audio_output)  # "It's 18 degrees and rainy in Tokyo."
```

### File System Assistant

```python
config = {
    "session": {
        "orchestrator": "loop-basic",
        "context": "context-simple"
    },
    "providers": [{
        "module": "provider-openai-realtime",
        "source": "git+https://github.com/robotdad/amplifier-module-provider-openai-realtime@main",
        "config": {
            "api_key": "${OPENAI_API_KEY}",
            "model": "gpt-4o-realtime-preview-2024-12-17",
            "voice": "alloy"
        }
    }],
    "tools": [{
        "module": "tool-filesystem",
        "source": "git+https://github.com/microsoft/amplifier-module-tool-filesystem@main",
        "config": {
            "base_path": "/home/user/documents"
        }
    }]
}

async def voice_file_assistant():
    """Voice assistant that can read/write files."""

    async with AmplifierSession(config=config) as session:
        # User: "Read the contents of notes.txt"
        audio_input = record_audio()

        response = await session.execute({
            "role": "user",
            "content": [{"type": "audio", "data": audio_input}]
        })

        # Model calls filesystem tool
        # Reads notes.txt
        # Speaks contents

        audio_output = response.raw["audio_data"]
        play_audio(audio_output)  # "Your notes say: Buy milk, call dentist..."
```

## Multi-Turn Tool Conversations

The provider handles multi-turn conversations with tool calls:

```python
async with AmplifierSession(config=config) as session:
    # Turn 1: User asks for weather
    response1 = await session.execute({
        "role": "user",
        "content": [{"type": "audio", "data": audio1}]
    })
    # → Calls weather tool
    # → Speaks: "It's 72 degrees in San Francisco"

    # Turn 2: User follows up
    response2 = await session.execute({
        "role": "user",
        "content": [{"type": "audio", "data": audio2}]
    })
    # Model remembers context (same session)
    # → "What about tomorrow?"
    # → Calls weather tool with forecast=true
    # → Speaks: "Tomorrow will be 68 degrees and cloudy"

    # Turn 3: User asks different question
    response3 = await session.execute({
        "role": "user",
        "content": [{"type": "audio", "data": audio3}]
    })
    # → "What files do I have?"
    # → Calls filesystem tool
    # → Speaks: "You have notes.txt, report.pdf, and data.csv"
```

**Key point**: Context preserved across turns via persistent WebSocket session.

## Tool Selection Strategies

### Natural Language Triggers

The model selects tools based on semantic understanding:

```python
# Filesystem tool
"Read my notes" → tool-filesystem.read_file
"Create a file called todo.txt" → tool-filesystem.write_file
"List my documents" → tool-filesystem.list_files

# Web tool
"Search for Python tutorials" → tool-web.search
"What's on Hacker News?" → tool-web.fetch

# Weather tool
"How's the weather?" → tool-weather.current
"Will it rain tomorrow?" → tool-weather.forecast
```

**No explicit commands needed** - model understands intent.

### Ambiguity Resolution

When multiple tools could apply:

```python
# User: "Get information about pandas"

# Model reasoning:
# - Could be web search for pandas (animal)
# - Could be web search for pandas (Python library)
# - Could be filesystem search for local files about pandas

# Model asks for clarification (voice):
# "Do you mean the Python library or the animal?"

# User responds (voice):
# "The Python library"

# Model calls: tool-web.search(query="pandas python library")
```

### Tool Chains

The model can chain multiple tools:

```python
# User: "Search for Python tutorials and save the best one to my reading list"

# Model execution:
# 1. tool-web.search(query="Python tutorials")
# 2. Analyzes results
# 3. tool-filesystem.write_file(
#       path="reading_list.txt",
#       content="Best tutorial: ..."
#    )
# 4. Speaks: "I found a great tutorial on Real Python and added it to your reading list"
```

## Error Handling

### Tool Execution Fails

```python
# Tool raises error
class WeatherTool:
    async def execute(self, location: str):
        if location == "unknown":
            raise ToolExecutionError("Location not found")

# Provider handles
try:
    tool_result = await tool_manager.execute(tool_call)
except ToolExecutionError as e:
    # Send error to model
    await websocket.send({
        "type": "conversation.item.create",
        "item": {
            "type": "function_call_output",
            "call_id": tool_call.id,
            "output": json.dumps({
                "error": str(e),
                "status": "failed"
            })
        }
    })

# Model speaks error gracefully:
# "I couldn't find weather information for that location. Could you try a different city?"
```

### Tool Not Available

```python
# User: "Search the web for information"
# But tool-web not configured

# Model response:
# "I don't have access to web search. I can help you with [available tools]."
```

### Invalid Arguments

```python
# Model calls tool with wrong arguments
tool_call = ToolCall(
    tool="get_weather",
    arguments={"city": "SF"},  # Wrong key, expects "location"
    id="call_123"
)

# Tool validation fails
# Error sent back to model
# Model retries with correct arguments:
tool_call = ToolCall(
    tool="get_weather",
    arguments={"location": "San Francisco"},
    id="call_124"
)
```

## Best Practices

### 1. Descriptive Tool Schemas

**GOOD**:
```python
{
    "name": "read_file",
    "description": "Read the contents of a text file from the filesystem",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to file (e.g., 'documents/notes.txt')"
            }
        },
        "required": ["path"]
    }
}
```

**BAD**:
```python
{
    "name": "read",  # Ambiguous
    "description": "Read file",  # Vague
    "parameters": {
        "type": "object",
        "properties": {
            "p": {"type": "string"}  # Unclear
        }
    }
}
```

### 2. Handle Missing Tools Gracefully

```python
# Don't configure tools user won't need
config = {
    "tools": [
        {"module": "tool-filesystem"},  # Always useful
        # Don't add tool-email unless user mentions email
    ]
}

# Model will naturally say:
# "I can't send emails, but I can help with files and documents"
```

### 3. Validate Tool Results

```python
class WeatherTool:
    async def execute(self, location: str):
        result = await fetch_weather(location)

        # Validate before returning
        if not result or "temperature" not in result:
            raise ToolExecutionError("Weather data incomplete")

        return result
```

### 4. Use Tool-Specific Voices

```python
# Different voices for different tool contexts
ASSISTANT_VOICE = "alloy"      # General conversation
TECHNICAL_VOICE = "echo"       # Code/technical tasks
CASUAL_VOICE = "shimmer"       # Casual file operations

# Switch voice based on tool being used
if tool_name == "tool-code":
    config["voice"] = TECHNICAL_VOICE
```

### 5. Limit Tool Scope

```python
# Filesystem tool with restricted access
{
    "module": "tool-filesystem",
    "config": {
        "base_path": "/home/user/documents",  # Can't access outside
        "readonly": False,
        "allowed_extensions": [".txt", ".md", ".json"]  # Only safe formats
    }
}
```

## Testing Tool Integration

### Unit Test: Tool Call Parsing

```python
def test_parse_tool_calls():
    """Test tool call extraction from response."""
    response = ProviderResponse(
        content="Using weather tool",
        raw={
            "websocket_response": {
                "type": "response.function_call_arguments.done",
                "call_id": "call_123",
                "name": "get_weather",
                "arguments": '{"location":"SF"}'
            }
        }
    )

    provider = OpenAIRealtimeProvider(...)
    tool_calls = provider.parse_tool_calls(response)

    assert len(tool_calls) == 1
    assert tool_calls[0].tool == "get_weather"
    assert tool_calls[0].arguments == {"location": "SF"}
    assert tool_calls[0].id == "call_123"
```

### Integration Test: Full Tool Flow

```python
async def test_voice_tool_execution():
    """Test voice → tool call → voice response."""
    config = {
        "providers": [{"module": "provider-openai-realtime", ...}],
        "tools": [{"module": "tool-weather", ...}]
    }

    async with AmplifierSession(config=config) as session:
        # Audio asking about weather
        audio_input = load_audio("weather_question.wav")

        response = await session.execute({
            "role": "user",
            "content": [{"type": "audio", "data": audio_input}]
        })

        # Verify tool was called
        assert "weather" in response.raw["transcript"].lower()

        # Verify audio output exists
        assert response.raw["audio_data"]
        assert len(response.raw["audio_data"]) > 0
```

## Troubleshooting

### Issue: Model not calling tools

**Cause**: Tool schema unclear or model doesn't understand need.

**Solution**: Improve tool description:
```python
# Before
"description": "Get weather"

# After
"description": "Get current weather conditions for any city. Use when user asks about weather, temperature, or conditions."
```

### Issue: Tool called with wrong arguments

**Cause**: Parameter descriptions unclear.

**Solution**: Add examples in descriptions:
```python
"location": {
    "type": "string",
    "description": "City name (e.g., 'San Francisco', 'Tokyo', 'London')"
}
```

### Issue: Tool results not incorporated in response

**Cause**: Tool result format unexpected.

**Solution**: Return structured data:
```python
# GOOD
return {"temperature": 72, "condition": "sunny"}

# BAD
return "72 degrees sunny"  # Hard for model to parse
```

## See Also

- [Architecture](ARCHITECTURE.md) - Module design overview
- [API Contract](API_CONTRACT.md) - Provider protocol
- [Examples](EXAMPLES.md) - Usage recipes
- [Session Lifecycle](SESSION_LIFECYCLE.md) - WebSocket management
