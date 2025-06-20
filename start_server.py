#!/usr/bin/env python3
"""
Startup script for the YouTube to HTML Summary FastAPI server.
This script checks dependencies and starts the server with proper error handling.
"""

import sys
import subprocess
import importlib.util

def check_dependency(module_name, package_name=None):
    """Check if a Python module is available."""
    if package_name is None:
        package_name = module_name
    
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        print(f"❌ {package_name} is not installed.")
        return False
    else:
        print(f"✅ {package_name} is available.")
        return True

def check_ollama():
    """Check if Ollama is running."""
    try:
        import requests
        response = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
        if response.status_code == 200:
            print("✅ Ollama is running.")
            return True
        else:
            print("❌ Ollama is not responding properly.")
            return False
    except Exception as e:
        print(f"❌ Ollama is not running or not accessible: {e}")
        return False

def check_ffmpeg():
    """Check if FFmpeg is installed."""
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ FFmpeg is available.")
            return True
        else:
            print("❌ FFmpeg is not working properly.")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("❌ FFmpeg is not installed or not in PATH.")
        return False

def main():
    """Main function to check dependencies and start the server."""
    print("🚀 YouTube to HTML Summary API v2.0")
    print("=" * 50)
    print("✨ Enhanced Features:")
    print("   • SQLite database storage")
    print("   • Real-time task filtering")
    print("   • Statistics dashboard")
    print("   • Iframe preview for completed tasks")
    print("   • Advanced task management")
    print("   • Background processing")
    print("=" * 50)
    
    # Check Python dependencies
    print("\n📦 Checking Python dependencies...")
    required_modules = [
        ('fastapi', 'FastAPI'),
        ('uvicorn', 'Uvicorn'),
        ('whisper', 'OpenAI Whisper'),
        ('pydub', 'Pydub'),
        ('yt_dlp', 'yt-dlp'),
        ('openai', 'OpenAI'),
        ('torch', 'PyTorch'),
        ('numpy', 'NumPy'),
        ('tqdm', 'tqdm'),
        ('requests', 'Requests')
    ]
    
    missing_deps = []
    for module, package in required_modules:
        if not check_dependency(module, package):
            missing_deps.append(package)
    
    if missing_deps:
        print(f"\n❌ Missing dependencies: {', '.join(missing_deps)}")
        print("Please install them using:")
        print("uv pip install fastapi uvicorn openai-whisper pydub yt-dlp openai torch numpy tqdm requests")
        sys.exit(1)
    
    # Check system dependencies
    print("\n🔧 Checking system dependencies...")
    if not check_ffmpeg():
        print("\nPlease install FFmpeg:")
        print("- macOS: brew install ffmpeg")
        print("- Ubuntu/Debian: sudo apt-get install ffmpeg")
        print("- Windows: Download from https://ffmpeg.org/download.html")
        sys.exit(1)
    
    if not check_ollama():
        print("\nPlease start Ollama:")
        print("1. Install Ollama from https://ollama.ai/")
        print("2. Pull the required model: ollama pull deepseek-r1:32b")
        print("3. Start Ollama: ollama serve")
        sys.exit(1)
    
    print("\n✅ All dependencies are satisfied!")
    print("\n🌐 Starting FastAPI server...")
    print("📱 Open your browser and navigate to: http://localhost:8000")
    print("📚 API documentation available at: http://localhost:8000/docs")
    print("📊 Database will be automatically created: youtube_summary.db")
    print("\n🎯 New Features:")
    print("   • Click 'Stats' button to view statistics dashboard")
    print("   • Use filter buttons to view tasks by status")
    print("   • Search tasks by video ID or title")
    print("   • Click 'Preview Result' to view HTML in iframe")
    print("   • Use 'Cleanup Old' to remove old tasks")
    print("\nPress Ctrl+C to stop the server.")
    print("=" * 50)
    
    # Start the server
    try:
        import uvicorn
        uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user.")
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 