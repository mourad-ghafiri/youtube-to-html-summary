#!/usr/bin/env python3
import os
import json
import uuid
import asyncio
from datetime import datetime
from typing import Dict, Optional, Any
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import concurrent.futures
import threading

# Import the processing functions from main.py
from main import (
    process_youtube_audio, 
    get_video_id, 
    setup_folder_structure, 
    get_output_paths,
    is_video_processed,
    setup_logging
)

# ================ Configuration ================
DEFAULT_OUTPUT_DIR = "downloads"
TASKS_FILE = "tasks.json"

# ================ Data Models ================
class VideoRequest(BaseModel):
    url: str

class TaskStatus(BaseModel):
    task_id: str
    video_id: str
    status: str
    progress: Dict[str, Any]
    created_at: str
    updated_at: str
    error: Optional[str] = None

# ================ Global State ================
# In-memory storage for task status (in production, use Redis or database)
tasks: Dict[str, TaskStatus] = {}
# Thread pool for CPU-intensive tasks
executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

# ================ FastAPI App ================
app = FastAPI(
    title="YouTube to HTML Summary API",
    description="Convert YouTube videos to structured HTML summaries",
    version="1.0.0"
)

# Mount static files for the frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

# ================ Utility Functions ================
def load_tasks():
    """Load tasks from file."""
    global tasks
    if os.path.exists(TASKS_FILE):
        try:
            with open(TASKS_FILE, 'r') as f:
                data = json.load(f)
                tasks = {k: TaskStatus(**v) for k, v in data.items()}
        except Exception as e:
            print(f"Error loading tasks: {e}")

def save_tasks():
    """Save tasks to file."""
    try:
        with open(TASKS_FILE, 'w') as f:
            json.dump({k: v.dict() for k, v in tasks.items()}, f, indent=2)
    except Exception as e:
        print(f"Error saving tasks: {e}")

def update_task_status(task_id: str, status: str, progress: Dict = None, error: str = None):
    """Update task status."""
    if task_id in tasks:
        tasks[task_id].status = status
        if progress:
            tasks[task_id].progress.update(progress)
        if error:
            tasks[task_id].error = error
        tasks[task_id].updated_at = datetime.now().isoformat()
        save_tasks()

def get_processing_progress(video_id: str, output_paths: Dict) -> Dict:
    """Get current processing progress based on existing files."""
    progress = {
        "audio_downloaded": False,
        "segments_created": False,
        "transcription_complete": False,
        "llm_processing_complete": False,
        "html_generated": False,
        "total_steps": 5,
        "completed_steps": 0
    }
    
    # Check each step
    if os.path.exists(output_paths['audio']):
        progress["audio_downloaded"] = True
        progress["completed_steps"] += 1
    
    if any(os.path.exists(f) for f in output_paths['segments']):
        progress["segments_created"] = True
        progress["completed_steps"] += 1
    
    if os.path.exists(output_paths['full_transcript_txt']):
        progress["transcription_complete"] = True
        progress["completed_steps"] += 1
    
    if os.path.exists(output_paths['processed_content']):
        progress["llm_processing_complete"] = True
        progress["completed_steps"] += 1
    
    if os.path.exists(output_paths['processed_html']):
        progress["html_generated"] = True
        progress["completed_steps"] += 1
    
    return progress

# ================ Synchronous Processing Function ================
def process_video_sync(task_id: str, url: str):
    """Synchronous processing function that runs in a thread pool."""
    logger = setup_logging()
    
    try:
        # Get video ID and set up paths
        video_id = get_video_id(url)
        folders = setup_folder_structure(DEFAULT_OUTPUT_DIR, video_id)
        output_paths = get_output_paths(folders, video_id)
        
        # Update initial status
        update_task_status(task_id, "processing", {
            "current_step": "Initializing",
            "message": "Starting video processing..."
        })
        
        # Check if already processed
        if is_video_processed(output_paths):
            update_task_status(task_id, "completed", {
                "current_step": "Completed",
                "message": "Video already processed",
                "html_path": output_paths['processed_html']
            })
            return
        
        # Step 1: Download audio
        update_task_status(task_id, "processing", {
            "current_step": "Downloading Audio",
            "message": "Downloading audio from YouTube..."
        })
        
        if not os.path.exists(output_paths['audio']):
            from main import download_audio
            download_audio(url, folders['audio'], logger)
        
        # Step 2: Split audio
        update_task_status(task_id, "processing", {
            "current_step": "Splitting Audio",
            "message": "Splitting audio into segments..."
        })
        
        if not any(os.path.exists(f) for f in output_paths['segments']):
            from main import split_audio
            split_audio(output_paths['audio'], folders['segments'], logger)
        
        # Step 3: Transcribe
        update_task_status(task_id, "processing", {
            "current_step": "Transcribing",
            "message": "Transcribing audio segments..."
        })
        
        if not os.path.exists(output_paths['full_transcript_txt']):
            from main import (
                whisper, transcribe_segment, save_segment_json,
                combine_transcriptions, extract_text_from_json
            )
            
            model = whisper.load_model("turbo")
            segment_files = [f for f in output_paths['segments'] if os.path.exists(f)]
            
            for i, segment_file in enumerate(segment_files):
                transcription_path = output_paths['transcriptions'][i]
                if not os.path.exists(transcription_path):
                    result = transcribe_segment(model, segment_file, logger)
                    save_segment_json(result, transcription_path, i + 1, logger)
                
                # Update progress for each segment
                progress = (i + 1) / len(segment_files) * 100
                update_task_status(task_id, "processing", {
                    "current_step": "Transcribing",
                    "message": f"Transcribing segment {i + 1}/{len(segment_files)}",
                    "progress_percent": progress
                })
            
            # Combine transcriptions
            segment_json_files = [f for f in output_paths['transcriptions'] if os.path.exists(f)]
            combine_transcriptions(segment_json_files, output_paths['full_transcript_json'], logger)
            extract_text_from_json(output_paths['full_transcript_json'], output_paths['full_transcript_txt'], logger)
        
        # Step 4: LLM Processing
        update_task_status(task_id, "processing", {
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
        update_task_status(task_id, "processing", {
            "current_step": "Generating HTML",
            "message": "Creating final HTML output..."
        })
        
        if not os.path.exists(output_paths['processed_html']):
            from main import generate_html
            generate_html(processed_content, output_paths['processed_html'])
        
        # Mark as completed
        update_task_status(task_id, "completed", {
            "current_step": "Completed",
            "message": "Video processing completed successfully",
            "html_path": output_paths['processed_html']
        })
        
    except Exception as e:
        logger.error(f"Error in background task: {e}")
        update_task_status(task_id, "failed", error=str(e))

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
        
        # Create task status
        task_status = TaskStatus(
            task_id=task_id,
            video_id=video_id,
            status="queued",
            progress={},
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        
        tasks[task_id] = task_status
        save_tasks()
        
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
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return tasks[task_id]

@app.get("/api/result/{task_id}")
async def get_result(task_id: str):
    """Get the HTML result for a completed task."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = tasks[task_id]
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="Task not completed")
    
    # Get the HTML file path
    folders = setup_folder_structure(DEFAULT_OUTPUT_DIR, task.video_id)
    output_paths = get_output_paths(folders, task.video_id)
    
    if not os.path.exists(output_paths['processed_html']):
        raise HTTPException(status_code=404, detail="HTML file not found")
    
    return FileResponse(
        output_paths['processed_html'],
        media_type='text/html',
        filename=f"{task.video_id}_summary.html"
    )

@app.get("/api/tasks", response_model=Dict[str, TaskStatus])
async def list_tasks():
    """List all tasks."""
    return tasks

@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    """Delete a task."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    del tasks[task_id]
    save_tasks()
    
    return {"message": "Task deleted successfully"}

# ================ Frontend Route ================
@app.get("/", response_class=HTMLResponse)
async def get_frontend():
    """Serve the frontend HTML page."""
    return FileResponse("static/index.html")

# ================ Startup Event ================
@app.on_event("startup")
async def startup_event():
    """Load tasks on startup."""
    load_tasks()

# ================ Shutdown Event ================
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    executor.shutdown(wait=True)

# ================ Main ================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000) 