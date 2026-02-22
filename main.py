import os
import glob
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import yt_dlp
import uuid
import re

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
                        'player_client': ['android'],
                    }
                },
            }
            with yt_dlp.YoutubeDL(ydl_opts_android) as ydl:
                info = ydl.extract_info(url, download=False)
                all_formats.extend(info.get('formats', []))
                print(f"Android client: {len(info.get('formats', []))} formats")
        except Exception as e:
            print(f"Android client failed: {e}")
        
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
                'player_client': ['android', 'web', 'ios'],
                'player_skip': ['webpage']
            }
        },
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'nocheckcertificate': True,
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
                'player_client': ['android', 'web'],
                'skip': ['hls', 'dash'],
                'player_skip': ['webpage', 'configs']
            }
        },
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'nocheckcertificate': True,
        'ignoreerrors': False,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        files = glob.glob(f"{base_name}*.mp3")
        if not files:
            raise Exception("File not found after download")
            
        info = ydl.extract_info(url, download=False)
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
