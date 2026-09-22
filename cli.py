#!/usr/bin/env python3
"""Voice Clone CLI - clone voices from YouTube and generate speech via OpenRouter/Voxtral."""

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

BASE_DIR = Path.home() / ".voice-clone"
VOICES_DIR = BASE_DIR / "voices"
CACHE_DIR = BASE_DIR / "cache"
API_KEY = os.environ.get("VOICE_CLONE_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or ""


def ensure_dirs():
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_voice_dir(name):
    return VOICES_DIR / name


def get_meta(voice_dir):
    meta_path = voice_dir / "meta.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text())
    return None


def save_meta(voice_dir, meta):
    meta_path = voice_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))


def cmd_add(args):
    """Download a YouTube video and save as a voice reference."""
    ensure_dirs()
    voice_dir = get_voice_dir(args.name)
    voice_dir.mkdir(parents=True, exist_ok=True)

    # Download audio
    tmp_path = BASE_DIR / f"_tmp_{args.name}.mp3"
    print(f"Downloading from YouTube: {args.url}")
    result = subprocess.run(
        ["yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "0",
         "-o", str(tmp_path), args.url],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Error downloading: {result.stderr}")
        sys.exit(1)

    # Get video info
    info = subprocess.run(
        ["yt-dlp", "--print", "title", "--print", "duration", args.url],
        capture_output=True, text=True
    )
    title = info.stdout.strip().split("\n")[0]

    # Trim
    ref_path = voice_dir / "ref.mp3"
    start = args.start or 30
    duration = args.duration or 15
    print(f"Trimming {duration}s from {start}s mark...")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(tmp_path), "-ss", str(start), "-t", str(duration),
         "-ac", "1", "-ar", "24000", str(ref_path)],
        capture_output=True
    )

    # Verify
    probe = subprocess.run(
        ["ffprobe", str(ref_path)], capture_output=True, text=True
    )
    for line in probe.stderr.split("\n"):
        if "Duration" in line:
            print(f"  Reference clip: {line.strip()}")

    # Save metadata
    save_meta(voice_dir, {
        "name": args.name,
        "youtube_url": args.url,
        "title": title,
        "start": start,
        "duration": duration,
    })

    # Cleanup
    tmp_path.unlink(missing_ok=True)
    print(f"Voice '{args.name}' saved to {voice_dir}")


def cmd_list(args):
    """List all cached voices."""
    ensure_dirs()
    voices = []
    for d in sorted(VOICES_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith("_"):
            meta = get_meta(d)
            if meta:
                ref_path = d / "ref.mp3"
                size = ref_path.stat().st_size if ref_path.exists() else 0
                voices.append(f"  {meta['name']:20s}  {meta.get('title', '?')[:50]:50s}  {size//1024}KB")
    
    if voices:
        print("Cached voices:")
        for v in voices:
            print(v)
    else:
        print("No voices cached. Use 'add' to create one.")


def cmd_remove(args):
    """Remove a cached voice."""
    voice_dir = get_voice_dir(args.name)
    if voice_dir.exists():
        import shutil
        shutil.rmtree(voice_dir)
        print(f"Removed voice '{args.name}'")
    else:
        print(f"Voice '{args.name}' not found")


def generate_speech(voice_dir, text, output_path, speed=None, normalize=False):
    """Generate speech via OpenRouter Voxtral with caching.
    
    If text is long (>1200 chars), auto-chunks on sentence boundaries to prevent
    voice energy dropping at the end of long generations (known Voxtral behavior).
    """
    if not API_KEY:
        print("Error: No API key set. Use VOICE_CLONE_API_KEY or OPENROUTER_API_KEY env var.")
        sys.exit(1)

    ensure_dirs()

    # Read reference audio
    ref_path = voice_dir / "ref.mp3"
    if not ref_path.exists():
        print(f"Error: reference audio not found for voice")
        sys.exit(1)

    with open(ref_path, "rb") as f:
        ref_audio_b64 = base64.b64encode(f.read()).decode()

    voice_name = voice_dir.name

    # Auto-chunk long text to maintain voice quality
    if len(text) > 1200:
        return _generate_chunked(voice_name, ref_audio_b64, text, output_path, speed, normalize)

    # Short text: single call
    cache_key = hashlib.sha256(f"{voice_name}:{text}".encode()).hexdigest()[:16]
    cache_path = CACHE_DIR / f"{cache_key}.mp3"

    if cache_path.exists():
        print(f"  (cached)")
        path = cache_path
    else:
        print(f"  Generating ({len(text)} chars)...")
        path = _call_voxtral(ref_audio_b64, text, cache_path)

    return _postprocess(path, output_path, speed, normalize)


def _call_voxtral(ref_audio_b64, text, cache_path):
    """Single Voxtral API call."""
    payload = {
        "model": "mistralai/voxtral-mini-tts-2603",
        "input": text,
        "voice": "alloy",
        "response_format": "mp3",
        "provider": {"options": {"mistral": {"ref_audio": ref_audio_b64}}}
    }

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/audio/speech",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            audio_data = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"API error ({e.code}): {body[:300]}")
        sys.exit(1)

    cache_path.write_bytes(audio_data)
    return cache_path


def _generate_chunked(voice_name, ref_audio_b64, text, output_path, speed, normalize):
    """Split long text into chunks at paragraph/sentence boundaries, generate each
    separately to maintain voice energy, then concatenate."""
    import re

    # Split on double newlines (paragraphs) then single newlines (section breaks)
    paragraphs = re.split(r'\n\n+', text)
    chunks = []
    current = ''

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # If adding this paragraph stays under ~1000 chars, merge it
        if len(current) + len(para) < 1000:
            current = (current + '\n\n' + para).strip()
        else:
            if current:
                chunks.append(current)
            # If single paragraph is too long, split on sentences
            if len(para) > 1200:
                sentences = re.split(r'(?<=[.!?])\s+', para)
                sub = ''
                for s in sentences:
                    if len(sub) + len(s) < 1000:
                        sub = (sub + ' ' + s).strip()
                    else:
                        if sub:
                            chunks.append(sub)
                        sub = s
                if sub:
                    chunks.append(sub)
            else:
                current = para
    if current:
        chunks.append(current)

    print(f"  Chunking into {len(chunks)} parts (avg {sum(len(c) for c in chunks)//len(chunks)} chars)...")

    chunk_paths = []
    for i, chunk in enumerate(chunks):
        cache_key = hashlib.sha256(f"{voice_name}:chunk{i}:{chunk}".encode()).hexdigest()[:16]
        cache_path = CACHE_DIR / f"{cache_key}.mp3"

        if cache_path.exists():
            print(f"    [{i+1}/{len(chunks)}] cached")
        else:
            print(f"    [{i+1}/{len(chunks)}] {len(chunk)} chars...")
            _call_voxtral(ref_audio_b64, chunk, cache_path)
        chunk_paths.append(cache_path)

    # Concatenate chunks
    concat_list = CACHE_DIR / "_concat.txt"
    with open(concat_list, 'w') as f:
        for p in chunk_paths:
            f.write(f"file '{p}'\n")

    merged_path = CACHE_DIR / f"merged_{hashlib.sha256(text.encode()).hexdigest()[:12]}.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-c", "copy", str(merged_path)],
        capture_output=True
    )

    return _postprocess(merged_path, output_path, speed, normalize)


def _postprocess(input_path, output_path, speed, normalize):
    """Apply speed adjustment and loudness normalization via ffmpeg."""
    if not speed and not normalize:
        if output_path and output_path != input_path:
            import shutil
            shutil.copy(input_path, output_path)
        return output_path or input_path

    filters = []
    if normalize:
        filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    if speed:
        filters.append(f"atempo={speed}")

    filter_str = ','.join(filters)
    final_path = output_path or input_path
    tmp_path = Path(str(final_path) + ".tmp.mp3")

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(input_path),
         "-filter:a", filter_str, "-b:a", "64k", str(tmp_path)],
        capture_output=True
    )
    tmp_path.replace(final_path)

    return final_path


def _get_duration(path):
    """Get accurate audio duration by decoding to PCM (Voxtral MP3s have
    unreliable header durations)."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0


def _clean_text(text):
    """Preprocess text for better TTS output: strip HTML, footnote refs,
    normalize spacing, add natural pauses."""
    import re
    # Strip HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Strip footnote references like [1], [2]
    text = re.sub(r'\[\d+\]', '', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Add breathing room after periods and question marks
    text = re.sub(r'([.!?])\s+', r'\1  ', text)
    return text


def cmd_speak(args):
    """Generate speech from a cloned voice."""
    voice_dir = get_voice_dir(args.name)
    if not voice_dir.exists():
        print(f"Voice '{args.name}' not found. Use 'add' first.")
        sys.exit(1)

    text = args.text
    if args.file:
        raw = Path(args.file).read_text().strip()
        text = _clean_text(raw) if not args.raw else raw

    if not text:
        print("No text provided.")
        sys.exit(1)

    output = Path(args.output) if args.output else Path(f"/tmp/{args.name}_speech.mp3")
    speed = float(args.speed) if args.speed else None
    normalize = args.normalize

    print(f"Generating speech for '{args.name}'...")
    path = generate_speech(voice_dir, text, output, speed=speed, normalize=normalize)

    duration = _get_duration(path)
    mins = int(duration // 60)
    secs = int(duration % 60)
    print(f"  Duration: {mins:02d}:{secs:02d}")
    print(f"  Saved to {path}")


def main():
    parser = argparse.ArgumentParser(description="Voice Clone CLI - clone voices from YouTube")
    sub = parser.add_subparsers(dest="command")

    # add
    p_add = sub.add_parser("add", help="Add a voice from a YouTube video")
    p_add.add_argument("name", help="Name for this voice")
    p_add.add_argument("url", help="YouTube URL")
    p_add.add_argument("--start", type=int, help="Start time in seconds (default: 30)")
    p_add.add_argument("--duration", type=int, help="Clip duration in seconds (default: 15)")

    # list
    p_list = sub.add_parser("list", help="List cached voices")

    # remove
    p_rm = sub.add_parser("remove", help="Remove a cached voice")
    p_rm.add_argument("name", help="Voice name to remove")

    # speak
    p_speak = sub.add_parser("speak", help="Generate speech with a cloned voice")
    p_speak.add_argument("name", help="Voice name to use")
    p_speak.add_argument("text", nargs="?", help="Text to speak")
    p_speak.add_argument("--file", "-f", help="Read text from file")
    p_speak.add_argument("--output", "-o", help="Output file path (default: /tmp/<name>_speech.mp3)")
    p_speak.add_argument("--speed", "-s", help="Playback speed multiplier (e.g. 0.95 for slower)")
    p_speak.add_argument("--normalize", "-n", action="store_true", help="Apply loudness normalization (loudnorm)")
    p_speak.add_argument("--raw", action="store_true", help="Skip text preprocessing (don't strip HTML/footnotes)")

    args = parser.parse_args()

    if args.command == "add":
        cmd_add(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "remove":
        cmd_remove(args)
    elif args.command == "speak":
        cmd_speak(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()