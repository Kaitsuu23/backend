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
from bs4 import BeautifulSoup
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
    """Get TikTok video information using web scraping"""
    try:
        # Clean the URL
        if '?' in url:
            clean_url = url.split('?')[0]
        else:
            clean_url = url
            
        # Check if it's a photo/slideshow URL (not supported)
        if '/photo/' in clean_url:
            raise HTTPException(
                status_code=400,
                detail="TikTok photo/slideshow tidak didukung. Hanya video TikTok yang bisa didownload."
            )
            
        print(f"Scraping TikTok info untuk: {clean_url}")
        
        # Headers untuk mimic browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.tiktok.com/',
        }
        
        # Request halaman TikTok
        print("Requesting TikTok page...")
        response = requests.get(clean_url, headers=headers, timeout=10)
        print(f"Response status: {response.status_code}")
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail=f"Tidak bisa mengakses TikTok. Status code: {response.status_code}"
            )
        
        # Parse HTML
        print("Parsing HTML...")
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Cari script tag yang berisi data video
        print("Looking for script tags...")
        script_tag = soup.find('script', {'id': '__UNIVERSAL_DATA_FOR_REHYDRATION__'})
        
        if not script_tag:
            print("__UNIVERSAL_DATA_FOR_REHYDRATION__ not found, trying SIGI_STATE...")
            # Coba cari di script tag lain
            script_tags = soup.find_all('script')
            for tag in script_tags:
                if tag.string and 'SIGI_STATE' in tag.string:
                    script_tag = tag
                    print("Found SIGI_STATE script tag")
                    break
        
        if not script_tag:
            print("ERROR: No script tag found with video data")
            print(f"HTML preview (first 500 chars): {response.text[:500]}")
            raise HTTPException(
                status_code=400,
                detail="Tidak bisa menemukan data video di halaman TikTok. Video mungkin private atau dihapus."
            )
        
        # Extract JSON data
        json_text = script_tag.string
        print(f"Script tag content preview: {json_text[:200] if json_text else 'None'}...")
        
        # Parse JSON
        if 'SIGI_STATE' in json_text:
            print("Parsing SIGI_STATE format...")
            # Extract JSON dari SIGI_STATE
            json_text = json_text.split('window[\'SIGI_STATE\']')[1].strip()
            json_text = json_text.split('window[\'SIGI_RETRY\']')[0].strip()
            json_text = json_text.strip('=;').strip()
        
        print("Parsing JSON...")
        data = json.loads(json_text)
        print(f"JSON keys: {list(data.keys())}")
        
        # Extract video info dari JSON
        video_detail = None
        
        # Coba berbagai struktur JSON yang mungkin
        if '__DEFAULT_SCOPE__' in data:
            print("Found __DEFAULT_SCOPE__")
            default_scope = data['__DEFAULT_SCOPE__']
            print(f"Default scope keys: {list(default_scope.keys())}")
            if 'webapp.video-detail' in default_scope:
                video_detail = default_scope['webapp.video-detail']['itemInfo']['itemStruct']
                print("Found video detail in webapp.video-detail")
        
        if not video_detail and 'ItemModule' in data:
            print("Trying ItemModule...")
            # Ambil video pertama dari ItemModule
            item_module = data['ItemModule']
            video_id = list(item_module.keys())[0]
            video_detail = item_module[video_id]
            print(f"Found video detail in ItemModule: {video_id}")
        
        if not video_detail:
            print(f"ERROR: Could not find video detail. Available keys: {list(data.keys())}")
            raise HTTPException(
                status_code=400,
                detail="Tidak bisa extract data video dari TikTok. Struktur JSON mungkin berubah."
            )
        
        print("Extracting video information...")
        
        # Extract informasi yang dibutuhkan
        title = video_detail.get('desc', 'TikTok Video')
        author = video_detail.get('author', {})
        username = author.get('uniqueId', 'Unknown')
        nickname = author.get('nickname', username)
        
        # Get video URL
        video_data = video_detail.get('video', {})
        download_url = video_data.get('downloadAddr', '')
        
        if not download_url:
            # Coba playAddr sebagai fallback
            download_url = video_data.get('playAddr', '')
        
        print(f"Download URL found: {bool(download_url)}")
        
        # Get thumbnail
        thumbnail = video_data.get('cover', '')
        if not thumbnail:
            thumbnail = video_data.get('dynamicCover', '')
        
        # Get duration
        duration = video_data.get('duration', 0)
        
        # Get video resolution/format
        width = video_data.get('width', 0)
        height = video_data.get('height', 0)
        resolution = f"{height}p" if height > 0 else "default"
        
        print(f"Berhasil scrape TikTok: {title} by @{username}")
        
        return {
            "title": title,
            "thumbnail": thumbnail,
            "channel": f"@{username} ({nickname})",
            "duration": duration,
            "description": title,
            "video_formats": [
                {
                    "resolution": resolution,
                    "format_id": "best",
                    "ext": "mp4",
                    "download_url": download_url
                }
            ],
            "platform": "tiktok"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_msg = str(e)
        full_traceback = traceback.format_exc()
        print(f"Error TikTok scraping: {error_msg}")
        print(f"Full traceback:\n{full_traceback}")
        
        raise HTTPException(
            status_code=400,
            detail=f"Error scraping TikTok: {error_msg}. Video mungkin private, dihapus, atau TikTok mengubah struktur halaman."
        )

@app.get("/tiktok/download")
def download_tiktok(url: str, background_tasks: BackgroundTasks, format_id: Optional[str] = "best", task_id: Optional[str] = None):
    """Download TikTok video using direct URL from scraping"""
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
        
        print(f"Mendownload video TikTok: {clean_url}")
        
        # Pertama, scrape untuk dapat download URL
        info_response = get_tiktok_info(clean_url)
        
        if not info_response.get('video_formats'):
            raise Exception("Tidak ada format video yang tersedia")
        
        download_url = info_response['video_formats'][0].get('download_url')
        
        if not download_url:
            raise Exception("Tidak bisa mendapatkan URL download")
        
        # Download file menggunakan requests
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.tiktok.com/',
        }
        
        download_progress[task_id] = {"status": "downloading", "progress": 0.1}
        
        response = requests.get(download_url, headers=headers, stream=True, timeout=30)
        
        if response.status_code != 200:
            raise Exception(f"Gagal download: status code {response.status_code}")
        
        # Save file
        file_path = f"{base_name}.mp4"
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        progress = downloaded / total_size
                        download_progress[task_id] = {"status": "downloading", "progress": progress}
        
        download_progress[task_id] = {"status": "completed", "progress": 1.0}
        
        # Generate safe filename
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', info_response.get('title', 'tiktok_video')).strip()
        if not safe_title:
            safe_title = str(uuid.uuid4())

        def cleanup_all():
            cleanup_files(base_name)
            download_progress.pop(task_id, None)

        background_tasks.add_task(cleanup_all)
        
        return FileResponse(file_path, filename=f"{safe_title}.mp4", media_type="video/mp4")
        
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
