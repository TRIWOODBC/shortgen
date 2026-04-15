# ShortGen

AI driven short-video generation CLI. It turns a plot or trending topic into a storyboard, calls external video APIs to generate clips, and can optionally add character reference images, narration, and background music.

## Current Scope

ShortGen currently focuses on a local command-line workflow:

1. Generate a storyboard from a plot or a trending topic
2. Generate scene videos through one configured provider
3. Optionally pre-generate character reference images
4. Optionally generate TTS narration / dialogue and background music
5. Merge clips and audio with FFmpeg

The project is usable as a prototype, but it is still under active iteration. Some capabilities described below are partial rather than fully production-hardened.

## Features

- Plot mode: turn a custom story idea into a storyboard and scene videos
- Trending mode: fetch hot topics and generate a short plot automatically
- Full mode: storyboard + character images + audio + final composition
- Multiple video providers:
  - Dreamina / Jimeng via Volcengine
  - Runway
  - Pika
- LLM abstraction for storyboard generation:
  - DeepSeek
  - GLM
  - Kimi
  - OpenAI-compatible APIs
- Background music from:
  - local music library
  - Suno API
  - Stable Audio API
- 9:16 vertical-video oriented output

## What Is Implemented vs Partial

Implemented:

- CLI entrypoint
- Storyboard generation
- Trending fetcher
- Video generation provider routing
- Character image generation and caching
- TTS and background music modules
- FFmpeg-based final merge

Partial / still evolving:

- Dreamina now preferentially uses generated character reference images for scene video generation, but consistency still depends on provider-side model behavior
- Audio is merged at a basic workflow level and may still need tighter scene-level timing alignment
- API integrations depend on external provider stability and quota settings

## Project Structure

```text
shortgen-1/
├── main.py
├── requirements.txt
├── .env.example
├── src/
│   ├── config.py
│   ├── models.py
│   ├── storyboard.py
│   ├── trending.py
│   ├── video_gen.py
│   ├── image_gen.py
│   ├── character_manager.py
│   ├── audio_gen.py
│   └── composer.py
├── assets/
│   └── music/
└── output/
    ├── videos/
    ├── storyboards/
    ├── images/
    ├── characters/
    ├── audios/
    └── final/
```

## Requirements

- Python 3.10+
- FFmpeg available in `PATH`
- At least one LLM API key
- At least one video provider configured

Install FFmpeg on macOS:

```bash
brew install ffmpeg
```

## Installation

```bash
pip install -r requirements.txt
cp .env.example .env
```

Then fill in `.env`.

Minimum required configuration:

```env
LLM_API_KEY=your_llm_api_key

# choose at least one video provider
VOLC_ACCESS_KEY=your_access_key
VOLC_SECRET_KEY=your_secret_key
# or
RUNWAY_API_KEY=your_runway_api_key
# or
PIKA_API_KEY=your_pika_api_key
```

Optional configuration for full mode:

```env
VOLC_TTS_APP_ID=your_tts_app_id
VOLC_TTS_ACCESS_TOKEN=your_tts_access_token
SUNO_API_KEY=your_suno_key
STABLE_AUDIO_API_KEY=your_stable_audio_key
NEWS_API_KEY=your_newsapi_key
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
```

## Supported Providers

### LLM providers

- `deepseek`
- `glm`
- `kimi`
- `openai`
- `custom` via `LLM_BASE_URL` and `LLM_MODEL`

### Video providers

- `dreamina`
- `runway`
- `pika`
- `auto` chooses in this order:
  1. Dreamina
  2. Runway
  3. Pika

The project now defaults to `dreamina`.

## Usage

Interactive mode:

```bash
python main.py -i
```

Generate video from a plot:

```bash
python main.py -p "一个年轻人独自在深夜的地铁站等车"
```

Generate full output:

```bash
python main.py -p "一个年轻人独自在深夜的地铁站等车" --full
```

Explicitly choose a provider:

```bash
python main.py -p "一个年轻人独自在深夜的地铁站等车" --provider dreamina
```

Read plot from file:

```bash
python main.py -f plot.txt --full
```

Generate from trending topics:

```bash
python main.py -t --full
```

Choose trending category:

```bash
python main.py -t -c tech --full
```

Disable optional modules in full mode:

```bash
python main.py -p "一个海边回忆故事" --full --no-audio
python main.py -p "一个海边回忆故事" --full --no-characters
```

## Output

Typical outputs:

- `output/storyboards/*.json`
- `output/videos/*.mp4`
- `output/characters/*.png`
- `output/audios/*.mp3`
- `output/final/*.mp4`

## Provider Notes

### Dreamina / Jimeng

Recommended for mainland China users. Configure:

```env
VOLC_ACCESS_KEY=your_access_key
VOLC_SECRET_KEY=your_secret_key
JIMENG_MODEL=jimeng_t2v_v30
VIDEO_PROVIDER=dreamina
```

### Runway

May require overseas network access depending on your environment.

### Pika

Useful for quick experiments, but behavior depends on current API limits and account quota.

## Trending Sources

Current fetcher behavior:

- If `NEWS_API_KEY` is configured, use NewsAPI
- Otherwise default to Weibo hot search

The codebase also contains Baidu and Zhihu fetcher implementations, but the default path currently prefers NewsAPI or Weibo.

## Development Notes

- This repository is a CLI-first prototype rather than a polished platform product
- External API behavior, request payloads, and quotas may change over time
- Full end-to-end success depends on valid credentials, available quota, and FFmpeg being installed
- If you want stable production output, expect to add more retries, validation, and provider-specific error handling

## Roadmap

- Improve scene-level audio timing
- Strengthen character-consistency flow into video generation
- Add subtitles
- Add Web UI
- Add more providers

## License

MIT
