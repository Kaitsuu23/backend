# RaiSaver Backend

FastAPI backend untuk download video/audio dari YouTube, TikTok, dan Instagram.

## Features

✅ **YouTube Downloader**
- Multiple resolutions: 1080p, 720p, 480p, 360p, 240p, 144p
- Audio download (MP3)
- Proxy support untuk bypass YouTube blocking
- Auto-merge video + audio dengan FFmpeg

✅ **TikTok Downloader**
- Video HD & SD quality
- Photo/slideshow download
- Menggunakan TikWM API (no cookies needed)

✅ **Instagram Downloader**
- Reels & Post video - via yt-dlp
- Photo posts & Carousel - via instaloader
- Memerlukan cookies untuk authentication

## Environment Variables

### Required for YouTube (Optional)
```bash
PROXY_URL=http://username:password@proxy-ip:port
```

### Required for Instagram
```bash
INSTAGRAM_COOKIES=<isi cookies.txt dari browser>
```

atau

```bash
INSTAGRAM_COOKIES_FROM_BROWSER=firefox
# atau
INSTAGRAM_COOKIES_FROM_BROWSER=chrome
```

## Setup Guides

- [Proxy Setup untuk YouTube](PROXY_SETUP.md)
- [Instagram Cookies Setup](INSTAGRAM_SETUP.md)
- [Deploy ke Railway](DEPLOY_RAILWAY.md)

## API Endpoints

### YouTube

**GET /info**
- Query: `url` (YouTube URL)
- Returns: Video info + available formats

**GET /download/video**
- Query: `url`, `format_id`, `task_id`
- Returns: Video file (MP4)

**GET /download/audio**
- Query: `url`, `task_id`
- Returns: Audio file (MP3)

### TikTok

**GET /tiktok/info**
- Query: `url` (TikTok URL)
- Returns: Video/photo info + download URLs

**GET /tiktok/download**
- Query: `url`, `format_id`, `task_id`
- Returns: Video (MP4) or Photo (JPG)

### Instagram

**GET /instagram/info**
- Query: `url` (Instagram URL)
- Returns: Video/photo info + formats
- **Requires:** INSTAGRAM_COOKIES environment variable

**GET /instagram/download**
- Query: `url`, `format_id`, `task_id`
- Returns: Video (MP4) or Photo (JPG)
- **Requires:** INSTAGRAM_COOKIES environment variable

### Progress

**GET /progress**
- Query: `task_id`
- Returns: Download progress (0.0 - 1.0)

## Dependencies

```
fastapi
uvicorn
yt-dlp
instaloader
requests
python-multipart
```

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run server
python main.py
```

Server akan jalan di `http://localhost:8000`

## Deploy to Railway

1. Connect GitHub repo ke Railway
2. Set environment variables (PROXY_URL, INSTAGRAM_COOKIES)
3. Railway akan auto-detect Dockerfile dan deploy

Lihat [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md) untuk detail lengkap.

## Troubleshooting

### YouTube hanya dapat 360p
- YouTube blocking Railway IP untuk video tertentu
- Coba gunakan proxy (set PROXY_URL)
- Beberapa video memang di-restrict oleh YouTube

### Instagram error "rate-limit reached"
- Cookies expired atau invalid
- Export ulang cookies dari browser
- Update INSTAGRAM_COOKIES di Railway

### TikTok error
- TikWM API down (jarang terjadi)
- URL TikTok invalid atau video dihapus

## Tech Stack

- **FastAPI** - Web framework
- **yt-dlp** - Video extractor (YouTube, Instagram)
- **TikWM API** - TikTok downloader
- **FFmpeg** - Video/audio processing
- **Uvicorn** - ASGI server
