# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Rules

- **All messages to users must be written in Russian (Русский язык).**
- **Never automatically run the application (GUI or CLI).** Only the user starts the application manually. Do not execute `python run_gui.py`, `aizoomdoc-gui`, or any `aizoomdoc` CLI commands without explicit user request.

## Development Commands

```bash
# Install in development mode
pip install -e .

# Install with dev dependencies (pytest, mypy)
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy src/

# Run GUI application
python run_gui.py
# Or after install:
aizoomdoc-gui
```

## Entry Points

- **CLI**: `aizoomdoc` command (src/aizoomdoc_client/cli.py) - Click-based CLI with Rich formatting
- **GUI**: `aizoomdoc-gui` or `python run_gui.py` (src/aizoomdoc_client/gui.py) - PyQt6 desktop app
- **Library**: `from aizoomdoc_client import AIZoomDocClient`

## Architecture

The codebase follows a layered architecture:

```
GUI/CLI Interface
    ↓
AIZoomDocClient (client.py)     - High-level API methods
    ↓
HTTPClient (http_client.py)     - HTTP transport, SSE streaming, auto token refresh
    ↓
ConfigManager (config.py)       - Token & config persistence (~/.aizoomdoc/config.json)
```

### Key Components

- **models.py**: Pydantic v2 models for API contracts (StreamEvent, ChatResponse, UserSettings, etc.)
- **exceptions.py**: Custom exception hierarchy (AIZoomDocError → AuthenticationError, APIError)

### Streaming Pattern

Messages use Server-Sent Events (SSE) via httpx-sse. The `send_message()` method yields `StreamEvent` objects. Key event types:
- `phase_started`: Processing phase transitions (search → processing → llm)
- `llm_token`: Individual tokens for real-time response streaming
- `tool_call`: AI tool invocations
- `completed`: Stream finished

### GUI Threading

`StreamWorker(QThread)` handles SSE streaming in background thread, emitting Qt signals:
- `token_received`, `phase_started`, `error_occurred`, `completed`
- ChatWidget connects to these signals to update UI without blocking

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `AIZOOMDOC_SERVER` | Override server URL (default: http://localhost:8000) |
| `AIZOOMDOC_TOKEN` | Static token for auto-authentication |

## Code Patterns

### Token Refresh
HTTPClient automatically refreshes expired JWT tokens on 401 responses, persisting new tokens via ConfigManager.

### ConfigManager Singleton
Use `get_config_manager()` to get the singleton instance. Stores server URL, tokens, and active chat ID.

### Adding New API Methods
1. Add method to `AIZoomDocClient` in client.py
2. If new data structure needed, add Pydantic model to models.py
3. For CLI exposure, add Click command to cli.py
4. For GUI exposure, integrate into appropriate widget in gui.py
