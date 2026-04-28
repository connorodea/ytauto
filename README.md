# ytauto

AI-powered YouTube video creation from a single prompt.

## Quick Start

```bash
# Install
uv pip install -e .

# Configure API keys
ytauto setup

# Check your environment
ytauto doctor

# Create a video
ytauto create "How banks secretly control the economy"
```

## Commands

| Command | Description |
|---------|-------------|
| `ytauto create "topic"` | Full end-to-end video creation pipeline |
| `ytauto script "topic"` | Generate a video script only |
| `ytauto voiceover <job-id>` | Generate voiceover for an existing job |
| `ytauto render <job-id>` | Render video from job assets |
| `ytauto jobs` | List all jobs |
| `ytauto job <job-id>` | Show job details |
| `ytauto resume <job-id>` | Resume a failed pipeline |
| `ytauto doctor` | Check dependencies and API keys |
| `ytauto setup` | Interactive API key configuration |

## Requirements

- Python 3.11+
- ffmpeg (for video rendering)
- At least one AI provider API key (Anthropic for scripts, OpenAI for TTS/images)
