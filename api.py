#!/usr/bin/env python3
import os
import json
import uuid
import asyncio
from datetime import datetime
from typing import Dict, Optional, Any, List
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import concurrent.futures
import threading
import yt_dlp

# Import the processing functions from main.py
from main import (
    process_youtube_audio, 
    get_video_id, 
    setup_folder_structure, 
    get_output_paths,
    is_video_processed,
    setup_logging
)

# Import database
from database import db

# ================ Configuration ================
DEFAULT_OUTPUT_DIR = "downloads"

# ================ Data Models ================
class VideoRequest(BaseModel):
    url: str

class TaskStatus(BaseModel):
    task_id: str
    video_id: str
    video_url: str
    video_title: Optional[str] = None
    status: str
    progress: Dict[str, Any]
    error_message: Optional[str] = None
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None
    processing_time: Optional[float] = None
    file_size: Optional[float] = None
    segments_count: Optional[int] = None
    transcription_length: Optional[int] = None

class TaskStats(BaseModel):
    total_tasks: int
    status_counts: Dict[str, int]
    avg_processing_time: float
    recent_tasks: int

# ================ Global State ================
# Thread pool for CPU-intensive tasks
executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

# ================ FastAPI App ================
app = FastAPI(
    title="YouTube to HTML Summary API",
    description="Convert YouTube videos to structured HTML summaries with database storage",
    version="2.0.0"
)

# Mount static files for the frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

# ================ Utility Functions ================
def get_video_info(url: str) -> Dict[str, str]:
    """Get video information using yt-dlp."""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title', 'Unknown Title'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0)
            }
    except Exception as e:
        print(f"Error getting video info: {e}")
        return {'title': 'Unknown Title', 'duration': 0, 'uploader': 'Unknown', 'view_count': 0}

def calculate_file_size(file_path: str) -> float:
    """Calculate file size in MB."""
    try:
        if os.path.exists(file_path):
            return os.path.getsize(file_path) / (1024 * 1024)
        return 0.0
    except:
        return 0.0

# ================ Synchronous Processing Function ================
def process_video_sync(task_id: str, url: str):
    """Synchronous processing function that runs in a thread pool."""
    logger = setup_logging()
    start_time = datetime.now()
    
    try:
        # Get video ID and set up paths
        video_id = get_video_id(url)
        folders = setup_folder_structure(DEFAULT_OUTPUT_DIR, video_id)
        output_paths = get_output_paths(folders, video_id)
        
        # Get video info and update database
        video_info = get_video_info(url)
        db.update_task_status(task_id, "processing", {
            "current_step": "Initializing",
            "message": "Starting video processing..."
        }, video_title=video_info['title'])
        
        # Check if already processed
        if is_video_processed(output_paths):
            processing_time = (datetime.now() - start_time).total_seconds()
            db.update_task_status(task_id, "completed", {
                "current_step": "Completed",
                "message": "Video already processed",
                "html_path": output_paths['processed_html']
            })
            db.update_task_metadata(task_id, processing_time=processing_time)
            return
        
        # Step 1: Download audio
        db.update_task_status(task_id, "processing", {
            "current_step": "Downloading Audio",
            "message": "Downloading audio from YouTube..."
        })
        
        if not os.path.exists(output_paths['audio']):
            from main import download_audio
            download_audio(url, folders['audio'], logger)
        
        # Step 2: Split audio
        db.update_task_status(task_id, "processing", {
            "current_step": "Splitting Audio",
            "message": "Splitting audio into segments..."
        })
        
        if not any(os.path.exists(f) for f in output_paths['segments']):
            from main import split_audio
            split_audio(output_paths['audio'], folders['segments'], logger)
        
        # Count segments
        segment_files = [f for f in output_paths['segments'] if os.path.exists(f)]
        db.update_task_metadata(task_id, segments_count=len(segment_files))
        
        # Step 3: Transcribe
        db.update_task_status(task_id, "processing", {
            "current_step": "Transcribing",
            "message": "Transcribing audio segments..."
        })
        
        if not os.path.exists(output_paths['full_transcript_txt']):
            from main import (
                whisper, transcribe_segment, save_segment_json,
                combine_transcriptions, extract_text_from_json
            )
            
            model = whisper.load_model("turbo")
            
            for i, segment_file in enumerate(segment_files):
                transcription_path = output_paths['transcriptions'][i]
                if not os.path.exists(transcription_path):
                    result = transcribe_segment(model, segment_file, logger)
                    save_segment_json(result, transcription_path, i + 1, logger)
                
                # Update progress for each segment
                progress = (i + 1) / len(segment_files) * 100
                db.update_task_status(task_id, "processing", {
                    "current_step": "Transcribing",
                    "message": f"Transcribing segment {i + 1}/{len(segment_files)}",
                    "progress_percent": progress
                })
            
            # Combine transcriptions
            segment_json_files = [f for f in output_paths['transcriptions'] if os.path.exists(f)]
            combine_transcriptions(segment_json_files, output_paths['full_transcript_json'], logger)
            extract_text_from_json(output_paths['full_transcript_json'], output_paths['full_transcript_txt'], logger)
        
        # Get transcription length
        if os.path.exists(output_paths['full_transcript_txt']):
            with open(output_paths['full_transcript_txt'], 'r', encoding='utf-8') as f:
                transcription_length = len(f.read())
            db.update_task_metadata(task_id, transcription_length=transcription_length)
        
        # Step 4: LLM Processing
        db.update_task_status(task_id, "processing", {
            "current_step": "LLM Processing",
            "message": "Processing with local LLM..."
        })
        
        if not os.path.exists(output_paths['processed_content']):
            from main import process_transcription_with_llm, PROMPT_TEMPLATE
            
            with open(output_paths['full_transcript_txt'], 'r', encoding='utf-8') as f:
                transcription_text = f.read()
            
            processed_content = process_transcription_with_llm(transcription_text, PROMPT_TEMPLATE, logger)
            
            with open(output_paths['processed_content'], 'w', encoding='utf-8') as f:
                f.write(processed_content)
        
        # Step 5: Generate HTML
        db.update_task_status(task_id, "processing", {
            "current_step": "Generating HTML",
            "message": "Creating final HTML output..."
        })
        
        if not os.path.exists(output_paths['processed_html']):
            from main import generate_html
            generate_html(processed_content, output_paths['processed_html'])
        
        # Calculate final metadata
        processing_time = (datetime.now() - start_time).total_seconds()
        file_size = calculate_file_size(output_paths['processed_html'])
        
        # Mark as completed
        db.update_task_status(task_id, "completed", {
            "current_step": "Completed",
            "message": "Video processing completed successfully",
            "html_path": output_paths['processed_html']
        })
        db.update_task_metadata(task_id, processing_time=processing_time, file_size=file_size)
        
    except Exception as e:
        logger.error(f"Error in background task: {e}")
        processing_time = (datetime.now() - start_time).total_seconds()
        db.update_task_status(task_id, "failed", error_message=str(e))
        db.update_task_metadata(task_id, processing_time=processing_time)

# ================ Background Task ================
async def process_video_background(task_id: str, url: str):
    """Background task to process YouTube video - runs in thread pool."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(executor, process_video_sync, task_id, url)

# ================ API Endpoints ================
@app.post("/api/process", response_model=Dict[str, str])
async def process_video(request: VideoRequest, background_tasks: BackgroundTasks):
    """Start processing a YouTube video."""
    try:
        # Validate URL
        from main import is_valid_youtube_url
        if not is_valid_youtube_url(request.url):
            raise HTTPException(status_code=400, detail="Invalid YouTube URL")
        
        # Generate task ID
        task_id = str(uuid.uuid4())
        video_id = get_video_id(request.url)
        
        # Create task in database
        if not db.create_task(task_id, video_id, request.url):
            raise HTTPException(status_code=500, detail="Failed to create task")
        
        # Start background task
        background_tasks.add_task(process_video_background, task_id, request.url)
        
        return {
            "task_id": task_id,
            "video_id": video_id,
            "status": "queued",
            "message": "Video processing started"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """Get the status of a processing task."""
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return TaskStatus(**task)

@app.get("/api/tasks", response_model=List[TaskStatus])
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100, description="Number of tasks to return"),
    offset: int = Query(0, ge=0, description="Number of tasks to skip")
):
    """List tasks with optional filtering."""
    tasks = db.get_tasks(status=status, limit=limit, offset=offset)
    return [TaskStatus(**task) for task in tasks]

@app.get("/api/stats", response_model=TaskStats)
async def get_stats():
    """Get task statistics."""
    stats = db.get_task_stats()
    return TaskStats(**stats)

@app.get("/api/result/{task_id}")
async def get_result(task_id: str):
    """Get the HTML result for a completed task (download)."""
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task['status'] != "completed":
        raise HTTPException(status_code=400, detail="Task not completed")
    
    # Get the HTML file path
    folders = setup_folder_structure(DEFAULT_OUTPUT_DIR, task['video_id'])
    output_paths = get_output_paths(folders, task['video_id'])
    
    if not os.path.exists(output_paths['processed_html']):
        raise HTTPException(status_code=404, detail="HTML file not found")
    
    return FileResponse(
        output_paths['processed_html'],
        media_type='text/html',
        filename=f"{task['video_id']}_summary.html"
    )

@app.get("/api/preview/{task_id}")
async def preview_result(task_id: str):
    """Preview the HTML result for a completed task (opens in browser)."""
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task['status'] != "completed":
        raise HTTPException(status_code=400, detail="Task not completed")
    
    # Get the HTML file path
    folders = setup_folder_structure(DEFAULT_OUTPUT_DIR, task['video_id'])
    output_paths = get_output_paths(folders, task['video_id'])
    
    if not os.path.exists(output_paths['processed_html']):
        raise HTTPException(status_code=404, detail="HTML file not found")
    
    # Read the HTML content and return it directly
    with open(output_paths['processed_html'], 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    return HTMLResponse(content=html_content)

@app.get("/api/events/{task_id}")
async def get_task_events(task_id: str, limit: int = Query(20, ge=1, le=100)):
    """Get events for a specific task."""
    events = db.get_task_events(task_id, limit=limit)
    return events

@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    """Delete a task."""
    if not db.delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"message": "Task deleted successfully"}

@app.post("/api/cleanup")
async def cleanup_old_tasks(days: int = Query(30, ge=1, le=365)):
    """Clean up old completed/failed tasks."""
    deleted_count = db.cleanup_old_tasks(days)
    return {"message": f"Cleaned up {deleted_count} old tasks"}

# ================ Frontend Route ================
@app.get("/", response_class=HTMLResponse)
async def get_frontend():
    """Serve the frontend HTML page."""
    return FileResponse("static/index.html")

# ================ Startup Event ================
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    print("🚀 YouTube to HTML Summary API starting...")
    print("📊 Database initialized")

# ================ Shutdown Event ================
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    executor.shutdown(wait=True)
    print("👋 Server shutdown complete")

# ================ Main ================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000) 