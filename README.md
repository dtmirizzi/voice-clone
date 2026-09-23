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

## Examples

### Narrate a blog post

```bash
# Clone Sam Rockwell's voice from his White Lotus monologue
voice-clone add sam "https://www.youtube.com/watch?v=iKfDTyE0zTA" --start 6

# Generate audio — auto-chunks long text, slows to natural pace, evens volume
voice-clone speak sam -f post.html --speed 0.95 --normalize -o post-audio.mp3
# Duration: 09:45  Saved to post-audio.mp3
```

### Build a voice library

```bash
voice-clone add keanu "https://www.youtube.com/watch?v=yqEFgIv-aqM"
voice-clone add sam "https://www.youtube.com/watch?v=iKfDTyE0zTA" --start 6
voice-clone add morgan "https://www.youtube.com/watch?v=..." --start 60 --duration 20

voice-clone list
# Cached voices:
#   keanu                 "Knock Knock" monologue - Keanu Reeves         170KB
#   morgan                Morgan Freeman interview clip                    220KB
#   sam                   Sam Rockwell monologue about being an Asian...   180KB
```

### Batch generate from a script

```bash
# Read lines from a file, speak each one
while IFS= read -r line; do
  voice-clone speak sam "$line" -o "line-$((i++)).mp3"
done < script.txt
```

### Pipe text from stdin

```bash
# Pipe any text directly to the speakers
echo "Server deployment complete" | voice-clone speak sam --play

# Pipe from another command
curl -s https://example.com/article.txt | voice-clone speak sam --play

# Read a file, pipe it in
cat meeting-notes.txt | voice-clone speak sam --speed 0.95 --normalize
```

### Play directly to speakers

```bash
# Generate and play — no file saved
voice-clone speak sam "Dinner is ready" --play

# From file, normalized and slowed, straight to speakers
voice-clone speak sam -f announcement.txt --speed 0.92 --normalize --play
```

### Generate with raw text (skip HTML stripping)

```bash
# Useful when your file has intentional formatting you want preserved
voice-clone speak sam -f markdown-post.md --raw
```

## Features

- **YouTube voice cloning** — download any video, trim a clean 15s clip, use it as a voice reference
- **Auto-chunking** — long text (>1200 chars) is split into sections, each generated fresh, then concatenated. Prevents the voice from losing energy at the end of long generations
- **Pipe-friendly** — reads from stdin when text is piped in: `echo "hello" | voice-clone speak sam --play`
- **Speaker output** — `--play` sends audio directly to system speakers via afplay (macOS), ffplay, or mpv
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