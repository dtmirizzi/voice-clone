# voice-clone

Clone a voice from any YouTube video and generate speech with it via OpenRouter's Voxtral TTS.

## Install

```bash
# Direct from GitHub (no PyPI needed)
uv tool install git+https://github.com/dtmirizzi/voice-clone.git

# Or via pip
pip install git+https://github.com/dtmirizzi/voice-clone.git
```

Requires `ffmpeg` and `yt-dlp` on your PATH:

```bash
brew install ffmpeg yt-dlp    # macOS
apt install ffmpeg yt-dlp     # Linux
```

## Quick start

```bash
# 1. Add a voice from any YouTube video (grabs a 15s clip at 30s mark)
voice-clone add sam "https://www.youtube.com/watch?v=iKfDTyE0zTA"

# 2. Speak
voice-clone speak sam "Hello, this is a test."

# 3. Read from a file
voice-clone speak sam -f blog-post.txt

# 4. Slow down + normalize volume
voice-clone speak sam -f blog-post.txt --speed 0.95 --normalize

# 5. Pick a custom clip location
voice-clone add morgan "https://youtube.com/..." --start 45 --duration 20
```

## Features

- **YouTube voice cloning** — download any video, trim a clean 15s clip, use it as a voice reference
- **Auto-chunking** — long text (>1200 chars) is split into sections, each generated fresh, then concatenated. Prevents the voice from losing energy at the end of long generations
- **Speed control** — `--speed 0.95` for natural pacing, applies ffmpeg atempo with pitch correction
- **Loudness normalization** — `--normalize` applies loudnorm (-16 LUFS) for consistent volume
- **Text preprocessing** — auto-strips HTML tags, footnote references, and normalizes spacing for better TTS
- **Caching** — every generation is cached by content hash. Re-running the same text is instant

## API

Uses OpenRouter's [Voxtral Mini TTS](https://openrouter.ai/mistralai/voxtral-mini-tts-2603) model. Requires an OpenRouter API key.

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
# or
export VOICE_CLONE_API_KEY="sk-or-v1-..."
```

## How it works

1. `add` downloads audio from YouTube via `yt-dlp`, trims a reference clip with `ffmpeg` (mono, 24kHz, 15 seconds)
2. `speak` sends text + reference audio to OpenRouter's Voxtral endpoint, which clones the voice and generates speech
3. Long text is auto-split at paragraph boundaries to maintain voice quality throughout
4. Post-processing applies speed adjustment and loudness normalization via `ffmpeg`

## Voices are stored locally

All voice data lives in `~/.voice-clone/voices/`. Nothing is uploaded except the reference audio sent with each API call. Cache lives at `~/.voice-clone/cache/`.

```bash
voice-clone list              # Show saved voices
voice-clone remove sam        # Delete a voice
```

## License

MIT