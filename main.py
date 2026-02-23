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
        
        # Strategy 1: Android client (usually has most formats)
        try:
            ydl_opts_android = {
                'quiet': True,
                'no_warnings': True,
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android_creator'],  # Try creator client
                    }
                },
                'geo_bypass': True,
                'geo_bypass_country': 'US',
                **get_ydl_proxy_opts(),
            }
            with yt_dlp.YoutubeDL(ydl_opts_android) as ydl:
                info = ydl.extract_info(url, download=False)
                all_formats.extend(info.get('formats', []))
                print(f"Android creator client: {len(info.get('formats', []))} formats")
        except Exception as e:
            print(f"Android creator client failed: {e}")
        
        # Strategy 2: iOS client
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
                all_formats.extend(info_ios.get('formats', []))
                print(f"iOS client: {len(info_ios.get('formats', []))} formats")
        except Exception as e:
            print(f"iOS client failed: {e}")
        
        # Strategy 3: Web client
        try:
            ydl_opts_web = {
                'quiet': True,
                'no_warnings': True,
                'extractor_args': {
                    'youtube': {
                        'player_client': ['web'],
                    }
                },
            }
            with yt_dlp.YoutubeDL(ydl_opts_web) as ydl:
                info_web = ydl.extract_info(url, download=False)
                all_formats.extend(info_web.get('formats', []))
                print(f"Web client: {len(info_web.get('formats', []))} formats")
        except Exception as e:
            print(f"Web client failed: {e}")
        
        print(f"Total formats from all clients: {len(all_formats)}")
        
        # Deduplicate and process formats
        video_resolutions = {}
        seen_format_ids = set()
        
        for f in all_formats:
            format_id = f.get('format_id')
            if format_id in seen_format_ids:
                continue
            seen_format_ids.add(format_id)
            
            # Get all video formats that have a URL
            if f.get('vcodec') != 'none' and f.get('url'):
                res = f.get('height')
                
                if res and res >= 144:
                    if res not in video_resolutions:
                        video_resolutions[res] = []
                    video_resolutions[res].append(format_id)
                    print(f"Added format {format_id}: {res}p")
        
        # Sort resolutions from highest to lowest
        sorted_res = sorted(video_resolutions.keys(), reverse=True)
        video_formats = [
            {
                "resolution": f"{r}p", 
                "format_id": video_resolutions[r][0]
            } 
            for r in sorted_res
        ]
        
        print(f"Final video_formats: {video_formats}")
        
        # Use info from first successful client
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

@app.get("/instagram/info")
def get_instagram_info(url: str):
    """Get Instagram post/story information using yt-dlp"""
    try:
        # Clean the URL
        if '?' in url:
            clean_url = url.split('?')[0]
        else:
            clean_url = url
            
        print(f"[Instagram] Extracting URL: {clean_url}")
        print(f"Fetching Instagram info for: {clean_url}")
        
        ydl_opts = {
            'quiet': False,
            'no_warnings': False,
            'nocheckcertificate': True,
            'extract_flat': 'discard_in_playlist',  # Don't use flat extraction
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            },
            **get_ydl_proxy_opts(),
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            
            # Debug: print full info structure
            print(f"Instagram info extracted: title={info.get('title')}, uploader={info.get('uploader')}, type={info.get('_type')}")
            print(f"Available keys in info: {list(info.keys())}")
            if info.get('_type') == 'playlist':
                print(f"Entries count: {len(info.get('entries', []))}")
                if info.get('entries'):
                    print(f"First entry keys: {list(info['entries'][0].keys()) if info['entries'][0] else 'None'}")
            print(f"Formats count: {len(info.get('formats', []))}")
            print(f"URL: {info.get('url')}")
            print(f"Thumbnail: {info.get('thumbnail')}")
            
            # Variables for metadata
            title = info.get('title', 'Instagram Post')
            thumbnail = info.get('thumbnail')
            username = info.get('uploader') or info.get('uploader_id') or info.get('channel')
            duration = info.get('duration', 0)
            description = info.get('description', '')
            
            # Handle playlist (carousel posts with multiple images/videos)
            is_carousel = info.get('_type') == 'playlist'
            video_formats = []
            is_video = False
            
            if is_carousel:
                entries = info.get('entries', [])
                print(f"Instagram carousel detected with {len(entries)} items")
                
                # If entries is empty, try to get formats from main info
                if not entries:
                    print("No entries found, checking main info for formats")
                    formats = info.get('formats', [])
                    
                    # Check if main info has formats (single image case)
                    if formats:
                        # Single image
                        best_format = None
                        for f in formats:
                            if f.get('url'):
                                if not best_format or (f.get('height', 0) > best_format.get('height', 0)):
                                    best_format = f
                        
                        if best_format:
                            video_formats.append({
                                "resolution": "Original",
                                "format_id": "best",
                                "ext": "jpg",
                                "download_url": best_format.get('url')
                            })
                            if not thumbnail:
                                thumbnail = best_format.get('url')
                    else:
                        # Try to get URL directly from info
                        img_url = info.get('url') or info.get('thumbnail')
                        if img_url:
                            video_formats.append({
                                "resolution": "Original",
                                "format_id": "best",
                                "ext": "jpg",
                                "download_url": img_url
                            })
                            if not thumbnail:
                                thumbnail = img_url
                else:
                    # Process entries
                    for idx, entry in enumerate(entries):
                        if entry:
                            # Check if entry is a video or image
                            entry_formats = entry.get('formats', [])
                            entry_is_video = any(f.get('vcodec') and f.get('vcodec') != 'none' for f in entry_formats)
                            
                            if entry_is_video:
                                is_video = True
                                # Get best video format URL
                                best_format = None
                                for f in entry_formats:
                                    if f.get('vcodec') != 'none' and f.get('url'):
                                        if not best_format or (f.get('height', 0) > best_format.get('height', 0)):
                                            best_format = f
                                
                                if best_format:
                                    video_formats.append({
                                        "resolution": f"Video {idx + 1}",
                                        "format_id": f"video_{idx}",
                                        "ext": "mp4",
                                        "download_url": best_format.get('url'),
                                        "entry_url": entry.get('url') or entry.get('webpage_url')
                                    })
                            else:
                                # Image - try multiple sources
                                img_url = None
                                if entry_formats:
                                    # Get URL from formats
                                    for f in entry_formats:
                                        if f.get('url'):
                                            img_url = f.get('url')
                                            break
                                
                                if not img_url:
                                    img_url = entry.get('url') or entry.get('thumbnail')
                                
                                if img_url:
                                    video_formats.append({
                                        "resolution": f"Image {idx + 1}",
                                        "format_id": f"img_{idx}",
                                        "ext": "jpg",
                                        "download_url": img_url,
                                        "entry_url": entry.get('url') or entry.get('webpage_url')
                                    })
                            
                            # Get thumbnail from first entry
                            if not thumbnail:
                                thumbnail = entry.get('thumbnail') or entry.get('url')
                                if not thumbnail and entry_formats:
                                    thumbnail = entry_formats[0].get('url')
                
                # Extract username from title if not available
                if not username and ' by ' in title:
                    username = title.split(' by ')[-1].strip()
                
            else:
                # Single post (video or image)
                formats = info.get('formats', [])
                print(f"Found {len(formats)} formats")
                
                # Check if it's a video or image
                for f in formats:
                    if f.get('vcodec') and f.get('vcodec') != 'none':
                        is_video = True
                        break
                
                if is_video:
                    # Get video formats
                    for f in formats:
                        if f.get('vcodec') != 'none' and f.get('url'):
                            res = f.get('height')
                            if res and res >= 144:
                                video_formats.append({
                                    "resolution": f"{res}p",
                                    "format_id": f.get('format_id'),
                                    "ext": f.get('ext', 'mp4')
                                })
                    
                    # Remove duplicates and sort
                    seen = set()
                    unique_formats = []
                    for fmt in video_formats:
                        if fmt['resolution'] not in seen:
                            seen.add(fmt['resolution'])
                            unique_formats.append(fmt)
                    
                    unique_formats.sort(key=lambda x: int(x['resolution'][:-1]), reverse=True)
                    video_formats = unique_formats
                    
                    # If no specific formats found, use best
                    if not video_formats:
                        video_formats.append({
                            "resolution": "Best",
                            "format_id": "best",
                            "ext": "mp4"
                        })
                else:
                    # Single image post
                    img_url = None
                    if formats:
                        # Get best quality image from formats
                        best_format = None
                        for f in formats:
                            if f.get('url'):
                                if not best_format or (f.get('height', 0) > best_format.get('height', 0)):
                                    best_format = f
                        if best_format:
                            img_url = best_format.get('url')
                    
                    if not img_url:
                        img_url = info.get('url') or info.get('thumbnail')
                    
                    video_formats = [{
                        "resolution": "Original",
                        "format_id": "best",
                        "ext": "jpg",
                        "download_url": img_url
                    }]
                
                # Extract username from title if not available
                if not username and ' by ' in title:
                    username = title.split(' by ')[-1].strip()
            
            print(f"Returning {len(video_formats)} unique formats, is_video: {is_video}")
            
            # Format username
            if not username:
                username = 'Unknown'
            if username and username != 'Unknown':
                username = f"@{username}" if not username.startswith('@') else username
            
            return {
                "title": title,
                "thumbnail": thumbnail,
                "channel": username,
                "duration": duration,
                "description": description,
                "video_formats": video_formats,
                "platform": "instagram",
                "is_carousel": is_carousel,
                "is_video": is_video
            }
            
    except Exception as e:
        import traceback
        error_msg = str(e)
        full_traceback = traceback.format_exc()
        print(f"Error Instagram info: {error_msg}")
        print(f"Full traceback:\n{full_traceback}")
        
        raise HTTPException(
            status_code=400,
            detail=f"Error mengambil info Instagram: {error_msg}"
        )

@app.get("/instagram/download")
def download_instagram(url: str, background_tasks: BackgroundTasks, format_id: Optional[str] = "best", task_id: Optional[str] = None):
    """Download Instagram post/story using yt-dlp"""
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
        
        print(f"Downloading Instagram: {clean_url}, format_id: {format_id}")
        
        # First, get info to check if we have direct download URL (for carousel items)
        info_response = get_instagram_info(clean_url)
        
        # Check if the selected format has a direct download_url
        download_url = None
        file_ext = "mp4"
        
        for fmt in info_response.get('video_formats', []):
            if fmt['format_id'] == format_id:
                download_url = fmt.get('download_url')
                file_ext = fmt.get('ext', 'mp4')
                break
        
        if download_url:
            # Direct download for carousel items
            print(f"Using direct download URL for carousel item")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.instagram.com/',
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
            
        else:
            # Use yt-dlp for regular posts
            def my_hook(d):
                if d['status'] == 'downloading':
                    total = d.get('total_bytes') or d.get('total_bytes_estimate', 1)
                    downloaded = d.get('downloaded_bytes', 0)
                    if total > 0:
                        download_progress[task_id] = {"status": "downloading", "progress": downloaded / total}
                elif d['status'] == 'finished':
                    download_progress[task_id] = {"status": "processing", "progress": 1.0}
            
            ydl_opts = {
                'format': format_id if format_id != "best" else 'best',
                'outtmpl': f"{base_name}.%(ext)s",
                'quiet': False,
                'progress_hooks': [my_hook],
                'nocheckcertificate': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                },
                **get_ydl_proxy_opts(),
            }
            
            print(f"Using yt-dlp for download")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(clean_url, download=True)
            
            files = glob.glob(f"{base_name}*")
            if not files:
                raise Exception("File tidak ditemukan setelah download")
            
            file_path = files[0]
            file_ext = file_path.split('.')[-1]
        
        # Generate simple filename: instagram_{timestamp}_img1.ext or instagram_{timestamp}.ext
        import time
        timestamp = str(int(time.time()))
        
        # Check if it's a carousel image
        if format_id.startswith('img_'):
            img_num = format_id.replace('img_', '')
            safe_title = f"instagram_{timestamp}_img{int(img_num) + 1}"
        elif format_id.startswith('video_'):
            vid_num = format_id.replace('video_', '')
            safe_title = f"instagram_{timestamp}_video{int(vid_num) + 1}"
        else:
            safe_title = f"instagram_{timestamp}"

        def cleanup_all():
            cleanup_files(base_name)
            download_progress.pop(task_id, None)

        background_tasks.add_task(cleanup_all)
        
        # Set appropriate media type
        if file_ext in ["jpg", "jpeg"]:
            media_type = "image/jpeg"
        elif file_ext == "png":
            media_type = "image/png"
        else:
            media_type = "video/mp4"
        
        final_filename = f"{safe_title}.{file_ext}"
        print(f"Final filename: {final_filename}")
        
        return FileResponse(file_path, filename=final_filename, media_type=media_type)
        
    except Exception as e:
        cleanup_files(base_name)
        download_progress.pop(task_id, None)
        error_msg = str(e)
        print(f"Error download Instagram: {error_msg}")
        
        raise HTTPException(
            status_code=400,
            detail=f"Gagal download Instagram: {error_msg}"
        )

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
