import os
import glob
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import yt_dlp
import uuid
import re
import requests
import json
from proxy_config import get_ydl_proxy_opts
from yt_dlp.utils import ExtractorError

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def cleanup_files(base_name: str):
    """Delete files starting with base_name"""
    for f in glob.glob(f"{base_name}*"):
        try:
            os.remove(f)
        except:
            pass

download_progress = {}

# Platform detection helper
def detect_platform(url: str) -> str:
    """Detect platform from URL"""
    if 'youtube.com' in url or 'youtu.be' in url:
        return 'youtube'
    elif 'tiktok.com' in url or 'vt.tiktok.com' in url:
        return 'tiktok'
    elif 'instagram.com' in url:
        return 'instagram'
    else:
        return 'unknown'

@app.get("/progress")
def get_progress(task_id: str):
    return download_progress.get(task_id, {"status": "starting", "progress": 0.0})

@app.get("/info")
def get_info(url: str):
    try:
        # Try multiple strategies to get all formats
        all_formats = []
        info = None
        
        # Strategy 1: Android creator client WITH proxy
        try:
            ydl_opts_android = {
                'quiet': True,
                'no_warnings': True,
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android_creator'],
                    }
                },
                'geo_bypass': True,
                'geo_bypass_country': 'US',
                **get_ydl_proxy_opts(),
            }
            with yt_dlp.YoutubeDL(ydl_opts_android) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = info.get('formats', [])
                all_formats.extend(formats)
                print(f"Android creator client (with proxy): {len(formats)} formats")
        except Exception as e:
            print(f"Android creator client failed: {e}")
        
        # Strategy 2: If we got less than 15 formats, try WITHOUT proxy
        if len(all_formats) < 15:
            try:
                print("Trying android_creator WITHOUT proxy...")
                ydl_opts_no_proxy = {
                    'quiet': True,
                    'no_warnings': True,
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['android_creator'],
                        }
                    },
                    'geo_bypass': True,
                    'geo_bypass_country': 'US',
                    # NO PROXY
                }
                with yt_dlp.YoutubeDL(ydl_opts_no_proxy) as ydl:
                    info_no_proxy = ydl.extract_info(url, download=False)
                    formats = info_no_proxy.get('formats', [])
                    all_formats.extend(formats)
                    if not info or len(formats) > len(info.get('formats', [])):
                        info = info_no_proxy
                    print(f"Android creator client (no proxy): {len(formats)} formats")
            except Exception as e:
                print(f"Android creator (no proxy) failed: {e}")
        
        # Strategy 3: Try android regular
        if len(all_formats) < 15:
            try:
                ydl_opts_android_regular = {
                    'quiet': True,
                    'no_warnings': True,
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['android'],
                        }
                    },
                    'geo_bypass': True,
                    'geo_bypass_country': 'US',
                    # Try without proxy
                }
                with yt_dlp.YoutubeDL(ydl_opts_android_regular) as ydl:
                    info_android = ydl.extract_info(url, download=False)
                    formats = info_android.get('formats', [])
                    all_formats.extend(formats)
                    if not info:
                        info = info_android
                    print(f"Android regular client: {len(formats)} formats")
            except Exception as e:
                print(f"Android regular client failed: {e}")
        
        # Strategy 4: iOS client
        if len(all_formats) < 15:
            try:
                ydl_opts_ios = {
                    'quiet': True,
                    'no_warnings': True,
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['ios'],
                        }
                    },
                }
                with yt_dlp.YoutubeDL(ydl_opts_ios) as ydl:
                    info_ios = ydl.extract_info(url, download=False)
                    formats = info_ios.get('formats', [])
                    all_formats.extend(formats)
                    if not info:
                        info = info_ios
                    print(f"iOS client: {len(formats)} formats")
            except Exception as e:
                print(f"iOS client failed: {e}")
        
        print(f"Total formats from all clients: {len(all_formats)}")
        
        # Filter for standard resolutions only
        standard_resolutions = {144, 240, 360, 480, 720, 1080, 1440, 2160}
        video_resolutions = {}
        seen_format_ids = set()
        
        for f in all_formats:
            format_id = f.get('format_id')
            if format_id in seen_format_ids:
                continue
            seen_format_ids.add(format_id)
            
            vcodec = f.get('vcodec', 'none')
            acodec = f.get('acodec', 'none')
            res = f.get('height')
            
            # Only include formats with standard resolutions
            if res and res in standard_resolutions:
                if vcodec != 'none' and f.get('url'):
                    if res not in video_resolutions:
                        video_resolutions[res] = []
                    
                    # Prioritize formats with audio
                    priority = 0 if acodec != 'none' else 1
                    video_resolutions[res].append((format_id, priority))
                    print(f"Added format {format_id}: {res}p (has_audio: {acodec != 'none'})")
        
        # Sort resolutions from highest to lowest
        sorted_res = sorted(video_resolutions.keys(), reverse=True)
        video_formats = []
        
        for r in sorted_res:
            # Sort by priority (formats with audio first)
            formats_for_res = sorted(video_resolutions[r], key=lambda x: x[1])
            video_formats.append({
                "resolution": f"{r}p", 
                "format_id": formats_for_res[0][0]
            })
        
        print(f"Final video_formats: {video_formats}")
        
        if not info:
            raise Exception("Failed to get video info from all clients")
        
        return {
            "title": info.get('title'),
            "thumbnail": info.get('thumbnail'),
            "channel": info.get('uploader'),
            "duration": info.get('duration'),
            "video_formats": video_formats
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/tiktok/info")
def get_tiktok_info(url: str):
    """Get TikTok video information using TikWM API"""
    try:
        # Clean the URL
        if '?' in url:
            clean_url = url.split('?')[0]
        else:
            clean_url = url
            
        print(f"Fetching TikTok info via TikWM API: {clean_url}")
        
        # Call TikWM API
        api_url = "https://www.tikwm.com/api/"
        params = {
            "url": clean_url,
            "hd": 1  # Request HD quality
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.post(api_url, data=params, headers=headers, timeout=15)
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail=f"TikWM API error: status code {response.status_code}"
            )
        
        data = response.json()
        print(f"TikWM API response: {data.get('code')}, msg: {data.get('msg')}")
        
        # Check if request was successful
        if data.get('code') != 0:
            error_msg = data.get('msg', 'Unknown error')
            raise HTTPException(
                status_code=400,
                detail=f"TikWM API error: {error_msg}"
            )
        
        # Extract video info
        video_data = data.get('data', {})
        
        title = video_data.get('title', 'TikTok Video')
        author = video_data.get('author', {})
        username = author.get('unique_id', 'Unknown')
        nickname = author.get('nickname', username)
        
        # Get video URLs
        play_url = video_data.get('play', '')  # Standard quality
        hdplay_url = video_data.get('hdplay', '')  # HD quality
        wmplay_url = video_data.get('wmplay', '')  # With watermark
        
        # Check if it's a photo/slideshow
        images = video_data.get('images', [])
        is_photo = len(images) > 0
        
        # Get thumbnail
        thumbnail = video_data.get('cover', '')
        if not thumbnail:
            thumbnail = video_data.get('origin_cover', '')
        
        # Get duration
        duration = video_data.get('duration', 0)
        
        # Get video stats
        play_count = video_data.get('play_count', 0)
        
        print(f"Berhasil fetch TikTok via TikWM: {title} by @{username}, is_photo: {is_photo}")
        
        # Build formats list
        video_formats = []
        
        if is_photo:
            # For photo/slideshow, return image URLs
            for idx, img_url in enumerate(images):
                video_formats.append({
                    "resolution": f"Image {idx + 1}",
                    "format_id": f"img_{idx}",
                    "ext": "jpg",
                    "download_url": img_url
                })
        else:
            # For video
            if hdplay_url:
                video_formats.append({
                    "resolution": "HD",
                    "format_id": "hd",
                    "ext": "mp4",
                    "download_url": hdplay_url
                })
            
            if play_url:
                video_formats.append({
                    "resolution": "SD",
                    "format_id": "sd",
                    "ext": "mp4",
                    "download_url": play_url
                })
        
        if not video_formats:
            raise HTTPException(
                status_code=400,
                detail="Tidak ada URL download yang tersedia dari TikWM API"
            )
        
        return {
            "title": title,
            "thumbnail": thumbnail,
            "channel": f"@{username} ({nickname})",
            "duration": duration,
            "description": title,
            "video_formats": video_formats,
            "platform": "tiktok",
            "play_count": play_count,
            "is_photo": is_photo
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_msg = str(e)
        full_traceback = traceback.format_exc()
        print(f"Error TikTok via TikWM: {error_msg}")
        print(f"Full traceback:\n{full_traceback}")
        
        raise HTTPException(
            status_code=400,
            detail=f"Error mengambil info TikTok: {error_msg}"
        )

# --- Instagram (yt-dlp: video + photo) ---

def _instagram_fetch_image_info(url: str):
    """Fetch Instagram photo post info via oEmbed (fallback when yt-dlp says no video)."""
    try:
        r = requests.get(
            "https://api.instagram.com/oembed",
            params={"url": url},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        # oEmbed returns thumbnail_url (can be the full-res image for single photo)
        image_url = data.get("thumbnail_url") or data.get("url")
        if not image_url:
            return None
        author = data.get("author_name") or "Instagram"
        title = data.get("title") or "Instagram Photo"
        return {
            "title": (title[:200] if title else "Instagram Photo"),
            "thumbnail": image_url,
            "channel": author,
            "duration": None,
            "video_formats": [
                {
                    "resolution": "Photo",
                    "format_id": "image",
                    "ext": "jpg",
                    "download_url": image_url,
                }
            ],
            "platform": "instagram",
            "is_photo": True,
        }
    except Exception as e:
        print(f"Instagram oEmbed fallback error: {e}")
        return None


@app.get("/instagram/info")
def get_instagram_info(url: str):
    """Get Instagram post/reel (video) or photo info using yt-dlp; photo fallback via oEmbed."""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        # Add cookie support from environment variable
        instagram_cookies = os.environ.get('INSTAGRAM_COOKIES', '')
        if instagram_cookies:
            # Support cookies from browser or cookies.txt format
            # User can set INSTAGRAM_COOKIES_FROM_BROWSER=firefox or chrome
            cookies_from_browser = os.environ.get('INSTAGRAM_COOKIES_FROM_BROWSER', '')
            if cookies_from_browser:
                ydl_opts['cookiesfrombrowser'] = (cookies_from_browser,)
                print(f"Using cookies from browser: {cookies_from_browser}")
            else:
                # Write cookies to temp file
                import tempfile
                cookie_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
                cookie_file.write(instagram_cookies)
                cookie_file.close()
                ydl_opts['cookiefile'] = cookie_file.name
                print(f"Using cookies from file: {cookie_file.name}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            raise Exception("Failed to extract Instagram info")

        # Handle playlist (carousel) - use first entry
        entries = info.get('entries')
        if entries:
            first = entries[0]
            if isinstance(first, dict) and first.get('url'):
                with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                    info = ydl2.extract_info(first['url'], download=False) or first
            elif isinstance(first, dict):
                info = first

        title = info.get('title') or info.get('description') or 'Instagram'
        uploader = info.get('uploader') or info.get('uploader_id') or 'Instagram'
        thumbnail = info.get('thumbnail') or ''
        duration = info.get('duration')

        formats = info.get('formats', [])
        video_formats = []
        if formats:
            height_set = set()
            for f in formats:
                h = f.get('height')
                if h and h not in height_set and f.get('vcodec') != 'none':
                    height_set.add(h)
                    video_formats.append({
                        'resolution': f'{h}p',
                        'format_id': f.get('format_id', 'best'),
                        'ext': f.get('ext', 'mp4'),
                    })
            video_formats.sort(key=lambda x: int(x['resolution'].replace('p', '') or 0), reverse=True)
        if not video_formats:
            video_formats = [{'resolution': 'Best', 'format_id': 'best', 'ext': 'mp4'}]
        return {
            'title': title[:200] if title else 'Instagram',
            'thumbnail': thumbnail,
            'channel': uploader,
            'duration': duration,
            'video_formats': video_formats,
            'platform': 'instagram',
        }
    except ExtractorError as e:
        msg = str(e)
        if 'There is no video in this post' in msg:
            # Photo-only post: fallback to oEmbed to get image URL
            fallback = _instagram_fetch_image_info(url)
            if fallback:
                return fallback
            raise HTTPException(
                status_code=400,
                detail="Tidak bisa mengambil info post foto Instagram. Coba link Reels/video.",
            )
        raise HTTPException(status_code=400, detail=f"Instagram extractor: {msg}")
    except Exception as e:
        import traceback
        print(f"Instagram info error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"Instagram: {str(e)}")

@app.get("/instagram/download")
def download_instagram(url: str, background_tasks: BackgroundTasks, format_id: Optional[str] = "best", task_id: Optional[str] = None):
    """Download Instagram video (yt-dlp) or photo (direct URL from info)."""
    if not task_id:
        task_id = str(uuid.uuid4())
    base_name = f"temp_ig_{task_id}"
    download_progress[task_id] = {"status": "starting", "progress": 0.0}

    # Photo: get info (hits oEmbed fallback), then download from download_url
    if format_id == "image":
        try:
            info_resp = get_instagram_info(url)
            formats = info_resp.get("video_formats") or []
            download_url = None
            file_ext = "jpg"
            for f in formats:
                if f.get("format_id") == "image" and f.get("download_url"):
                    download_url = f["download_url"]
                    file_ext = f.get("ext", "jpg")
                    break
            if not download_url:
                raise HTTPException(status_code=400, detail="URL foto tidak ditemukan.")
            download_progress[task_id] = {"status": "downloading", "progress": 0.1}
            r = requests.get(download_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, stream=True, timeout=30)
            if r.status_code != 200:
                raise Exception(f"Gagal download foto: HTTP {r.status_code}")
            file_path = f"{base_name}.{file_ext}"
            total_size = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(file_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            download_progress[task_id] = {"status": "downloading", "progress": downloaded / total_size}
            download_progress[task_id] = {"status": "completed", "progress": 1.0}
            safe_title = re.sub(r'[\\/:*?"<>|]', '_', (info_resp.get("title") or info_resp.get("channel") or "instagram")).strip() or f"instagram_{task_id}"
            media_type = "image/jpeg" if file_ext in ("jpg", "jpeg") else "image/png"

            def cleanup_all():
                cleanup_files(base_name)
                download_progress.pop(task_id, None)
            background_tasks.add_task(cleanup_all)
            return FileResponse(file_path, filename=f"{safe_title}.{file_ext}", media_type=media_type)
        except HTTPException:
            raise
        except Exception as e:
            cleanup_files(base_name)
            download_progress.pop(task_id, None)
            raise HTTPException(status_code=400, detail=f"Instagram photo download: {str(e)}")

    # Video: yt-dlp
    def my_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 1)
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                download_progress[task_id] = {"status": "downloading", "progress": downloaded / total}
        elif d['status'] == 'finished':
            download_progress[task_id] = {"status": "processing", "progress": 1.0}

    ydl_opts = {
        'format': format_id if format_id and format_id != 'best' else 'best[ext=mp4]/best',
        'outtmpl': f"{base_name}.%(ext)s",
        'quiet': True,
        'progress_hooks': [my_hook],
        'nocheckcertificate': True,
    }
    
    # Add cookie support for download too
    instagram_cookies = os.environ.get('INSTAGRAM_COOKIES', '')
    if instagram_cookies:
        cookies_from_browser = os.environ.get('INSTAGRAM_COOKIES_FROM_BROWSER', '')
        if cookies_from_browser:
            ydl_opts['cookiesfrombrowser'] = (cookies_from_browser,)
        else:
            import tempfile
            cookie_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
            cookie_file.write(instagram_cookies)
            cookie_file.close()
            ydl_opts['cookiefile'] = cookie_file.name
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        files = glob.glob(f"{base_name}*")
        files = [f for f in files if not f.endswith('.part') and os.path.isfile(f)]
        if not files:
            raise Exception("File not found after download")
        file_path = files[0]
        ext = file_path.split('.')[-1]
        info = None
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
            if info and info.get('entries'):
                info = info['entries'][0] if isinstance(info['entries'][0], dict) else info
        except Exception:
            pass
        safe_title = 'instagram'
        if info:
            safe_title = re.sub(r'[\\/:*?"<>|]', '_', (info.get('title') or info.get('uploader') or 'instagram')).strip() or 'instagram'
        if not safe_title or safe_title == 'instagram':
            safe_title = f"instagram_{task_id}"

        def cleanup_all():
            cleanup_files(base_name)
            download_progress.pop(task_id, None)
        background_tasks.add_task(cleanup_all)

        media_type = "video/mp4" if ext in ('mp4', 'webm') else "image/jpeg" if ext in ('jpg', 'jpeg') else "image/png"
        return FileResponse(file_path, filename=f"{safe_title}.{ext}", media_type=media_type)
    except ExtractorError as e:
        cleanup_files(base_name)
        download_progress.pop(task_id, None)
        msg = str(e)
        if 'There is no video in this post' in msg:
            raise HTTPException(
                status_code=400,
                detail="Post ini hanya foto. Gunakan tombol Download Photo di layar info.",
            )
        raise HTTPException(status_code=400, detail=f"Instagram extractor: {msg}")
    except Exception as e:
        cleanup_files(base_name)
        download_progress.pop(task_id, None)
        raise HTTPException(status_code=400, detail=f"Instagram download: {str(e)}")

@app.get("/tiktok/download")
def download_tiktok(url: str, background_tasks: BackgroundTasks, format_id: Optional[str] = "hd", task_id: Optional[str] = None):
    """Download TikTok video or photo using TikWM API"""
    if not task_id:
        task_id = str(uuid.uuid4())
    base_name = f"temp_{task_id}"

    download_progress[task_id] = {"status": "starting", "progress": 0.0}
    
    try:
        # Clean the URL
        if '?' in url:
            clean_url = url.split('?')[0]
        else:
            clean_url = url
        
        print(f"Downloading TikTok via TikWM: {clean_url}")
        
        # Get video/photo info first
        info_response = get_tiktok_info(clean_url)
        
        if not info_response.get('video_formats'):
            raise Exception("Tidak ada format yang tersedia")
        
        is_photo = info_response.get('is_photo', False)
        
        # Find the requested format
        download_url = None
        file_ext = "mp4"
        format_resolution = ""
        
        for fmt in info_response['video_formats']:
            if fmt['format_id'] == format_id:
                download_url = fmt['download_url']
                file_ext = fmt.get('ext', 'mp4')
                format_resolution = fmt.get('resolution', '')
                break
        
        # If format not found, use first available
        if not download_url:
            download_url = info_response['video_formats'][0]['download_url']
            file_ext = info_response['video_formats'][0].get('ext', 'mp4')
            format_resolution = info_response['video_formats'][0].get('resolution', '')
        
        if not download_url:
            raise Exception("Tidak bisa mendapatkan URL download")
        
        print(f"Download URL: {download_url[:50]}..., ext: {file_ext}")
        
        # Download file
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.tikwm.com/',
        }
        
        download_progress[task_id] = {"status": "downloading", "progress": 0.1}
        
        response = requests.get(download_url, headers=headers, stream=True, timeout=30)
        
        if response.status_code != 200:
            raise Exception(f"Gagal download: status code {response.status_code}")
        
        # Save file
        file_path = f"{base_name}.{file_ext}"
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        print(f"Downloading file, size: {total_size} bytes")
        
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        progress = downloaded / total_size
                        download_progress[task_id] = {"status": "downloading", "progress": progress}
        
        download_progress[task_id] = {"status": "completed", "progress": 1.0}
        
        print(f"Download completed: {downloaded} bytes")
        
        # Generate simple filename: tiktok_{timestamp}_{type}.ext
        import time
        timestamp = str(int(time.time()))
        
        if is_photo:
            # For photo: tiktok_{timestamp}_img1.jpg
            img_num = format_resolution.replace('Image ', '').strip() if 'Image' in format_resolution else '1'
            safe_title = f"tiktok_{timestamp}_img{img_num}"
        else:
            # For video: tiktok_{timestamp}.mp4
            safe_title = f"tiktok_{timestamp}"

        def cleanup_all():
            cleanup_files(base_name)
            download_progress.pop(task_id, None)

        background_tasks.add_task(cleanup_all)
        
        # Set appropriate media type
        if file_ext == "jpg" or file_ext == "jpeg":
            media_type = "image/jpeg"
        elif file_ext == "png":
            media_type = "image/png"
        else:
            media_type = "video/mp4"
        
        final_filename = f"{safe_title}.{file_ext}"
        print(f"Final filename: {final_filename}")
        
        return FileResponse(file_path, filename=final_filename, media_type=media_type)
        
    except HTTPException:
        cleanup_files(base_name)
        download_progress.pop(task_id, None)
        raise
    except Exception as e:
        cleanup_files(base_name)
        download_progress.pop(task_id, None)
        error_msg = str(e)
        print(f"Error download TikTok: {error_msg}")
        
        raise HTTPException(
            status_code=400,
            detail=f"Gagal download TikTok: {error_msg}"
        )

@app.get("/download/video")
def download_video(url: str, format_id: str, background_tasks: BackgroundTasks, task_id: Optional[str] = None):
    if not task_id:
        task_id = str(uuid.uuid4())
    base_name = f"temp_{task_id}"

    download_progress[task_id] = {"status": "starting", "progress": 0.0}

    def my_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 1)
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                download_progress[task_id] = {"status": "downloading", "progress": downloaded / total}
        elif d['status'] == 'finished':
            download_progress[task_id] = {"status": "processing", "progress": 1.0}
    
    # +bestaudio/best merges the selected video format with best available audio
    ydl_opts = {
        'format': f"{format_id}+bestaudio[ext=m4a]/bestaudio/best",
        'outtmpl': f"{base_name}.%(ext)s",
        'merge_output_format': 'mp4',
        'quiet': True,
        'writethumbnail': True,
        'progress_hooks': [my_hook],
        'postprocessors': [
            {'key': 'FFmpegMetadata'},
            {'key': 'EmbedThumbnail'},
        ],
        'extractor_args': {
            'youtube': {
                'player_client': ['android_creator'],  # Same as info endpoint
            }
        },
        'geo_bypass': True,
        'geo_bypass_country': 'US',
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'nocheckcertificate': True,
        **get_ydl_proxy_opts(),  # Add proxy support
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        # The downloaded file might end up with .mp4 or .mkv depending on what was fetched
        files = glob.glob(f"{base_name}*")
        if not files:
            raise Exception("File not found after download")
            
        def cleanup_all():
            cleanup_files(base_name)
            download_progress.pop(task_id, None)

        file_path = files[0]
        # Clean up file after streaming response
        background_tasks.add_task(cleanup_all)
        
        info = ydl.extract_info(url, download=False)
        # Only replace invalid filename characters, keep spaces
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', info.get('title', 'video')).strip()
        if not safe_title:
            safe_title = str(uuid.uuid4())

        # Determine media type based on extension
        ext = file_path.split('.')[-1]
        media_type = "video/mp4" if ext == "mp4" else "video/x-matroska"
        return FileResponse(file_path, filename=f"{safe_title}.{ext}", media_type=media_type)
    except Exception as e:
        cleanup_files(base_name)
        download_progress.pop(task_id, None)
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/download/audio")
def download_audio(url: str, background_tasks: BackgroundTasks, task_id: Optional[str] = None):
    if not task_id:
        task_id = str(uuid.uuid4())
    base_name = f"temp_{task_id}"

    download_progress[task_id] = {"status": "starting", "progress": 0.0}

    def my_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 1)
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                download_progress[task_id] = {"status": "downloading", "progress": downloaded / total}
        elif d['status'] == 'finished':
            download_progress[task_id] = {"status": "processing", "progress": 1.0}
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f"{base_name}.%(ext)s",
        'quiet': True,
        'writethumbnail': True,
        'progress_hooks': [my_hook],
        'postprocessors': [
            {
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            },
            {'key': 'FFmpegMetadata'},
            {'key': 'EmbedThumbnail'},
        ],
        'extractor_args': {
            'youtube': {
                'player_client': ['android_creator'],
            }
        },
        'geo_bypass': True,
        'geo_bypass_country': 'US',
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'nocheckcertificate': True,
        **get_ydl_proxy_opts(),  # Add proxy support
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        files = glob.glob(f"{base_name}*.mp3")
        if not files:
            raise Exception("File not found after download")
            
        info = ydl.extract_info(url, download=False)
        # Only replace invalid filename characters, keep spaces
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', info.get('title', 'audio')).strip()
        if not safe_title:
            safe_title = str(uuid.uuid4())

        def cleanup_all():
            cleanup_files(base_name)
            download_progress.pop(task_id, None)

        file_path = files[0]
        background_tasks.add_task(cleanup_all)
        return FileResponse(file_path, filename=f"{safe_title}.mp3", media_type="audio/mpeg")
    except Exception as e:
        cleanup_files(base_name)
        download_progress.pop(task_id, None)
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
