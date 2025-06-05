#!/usr/bin/env python3
import os
import sys
import json
import logging
import yt_dlp
import whisper
import re
from datetime import datetime
from pydub import AudioSegment
from urllib.parse import urlparse, parse_qs
from typing import Dict, List
import openai

# ================ Configuration ================
DEFAULT_OUTPUT_DIR = "downloads"
AUDIO_QUALITY = "320kbps"  # Best audio quality
SEGMENT_LENGTH = 20000  # 20 seconds in milliseconds
SEGMENT_OVERLAP = 2000  # 2 seconds overlap in milliseconds

# Folder Structure Configuration
FOLDER_STRUCTURE = {
    'video': 'video',           # Original video file
    'audio': 'audio',           # Downloaded audio file
    'segments': 'segments',     # Audio segments
    'transcriptions': 'transcriptions',  # Individual segment transcriptions
    'full_transcriptions': 'full_transcriptions',  # Combined transcriptions
    'processed': 'processed'    # Final processed content
}

# Local Model Configuration  
LOCAL_MODEL_URL = "http://127.0.0.1:11434"
LOCAL_MODEL_NAME = "deepseek-r1:32b"

# HTML Template for Output
HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <style>
        body {{
            font-family: serif;
            line-height: 1.6;
            margin: 0;
            padding: 2cm;
            color: #333;
            background: #fff;
        }}
        
        h1 {{
            font-family: serif;
            font-size: 24px;
            color: #2E4057;
            text-align: center;
            margin-bottom: 30px;
            border-bottom: 2px solid #2E4057;
            padding-bottom: 10px;
        }}
        
        h2 {{
            font-family: serif;
            font-size: 20px;
            color: #2E4057;
            margin-top: 25px;
            margin-bottom: 15px;
            border-right: 3px solid #2E4057;
            padding-right: 10px;
        }}
        
        h3 {{
            font-family: serif;
            font-size: 16px;
            color: #34495E;
            margin-top: 20px;
            margin-bottom: 10px;
        }}
        
        p {{
            font-family: serif;
            margin: 10px 0;
            text-align: justify;
        }}
        
        ul, ol {{
            font-family: serif;
            margin: 10px 0;
            padding-right: 20px;
        }}
        
        li {{
            font-family: serif;
            margin: 5px 0;
        }}
        
        .section {{
            margin: 20px 0;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 5px;
        }}
        
        .highlight {{
            background: #fff3cd;
            padding: 2px 5px;
            border-radius: 3px;
        }}
        
        .question {{
            background: #e3f2fd;
            padding: 10px;
            margin: 10px 0;
            border-radius: 5px;
        }}
        
        .answer {{
            background: #f1f8e9;
            padding: 10px;
            margin: 10px 0;
            border-radius: 5px;
        }}
        
        .emoji {{
            font-size: 1.2em;
            margin-left: 5px;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background-color: #fff;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        
        th, td {{
            padding: 12px;
            text-align: right;
            border: 1px solid #ddd;
        }}
        
        th {{
            background-color: #2E4057;
            color: white;
            font-weight: bold;
        }}
        
        tr:nth-child(even) {{
            background-color: #f8f9fa;
        }}
        
        tr:hover {{
            background-color: #f5f5f5;
        }}
    </style>
</head>
<body>
    {content}
</body>
</html>
"""

# Prompt template included directly
PROMPT_TEMPLATE = """I have a raw video transcription between triple backticks below. It may contain errors, repetitions, or incomplete sentences, but it captures the core of an important conversation. Your job is to carefully analyze and deeply understand the content and transform it into a rich, structured, unforgettable learning experience.

```
[PASTE TRANSCRIPTION HERE]
```

Your Role  
Act as a world-class educator, cognitive scientist, and instructional designer combined. Your mission is to preserve every valuable idea and enhance its clarity, memorability, and practical value.

Strict Output Rules  
- Output must be valid HTML
- Use the following HTML structure and CSS classes:
  - Main sections: <div class="section">
  - Questions: <div class="question">
  - Answers: <div class="answer">
  - Highlights: <span class="highlight">
  - Emojis: <span class="emoji">
  - Tables: Use proper <table>, <thead>, <tbody>, <tr>, <th>, and <td> tags
- Do not include any introductory or transitional phrases
- Do not explain, elaborate on, or add from your own knowledge
- Only use the content found within the transcription

OUTPUT INSTRUCTIONS

Deep Comprehension & Full Extraction  
- Read the entire transcription with attention to every unique idea, argument, concept, model, or paradigm  
- Include all meaningful content, even if repeated. No summarization that omits ideas

Break Down & Present Ideas Using Modern Techniques  
1. Organize the content into a structured outline with clear section headers using <h1>, <h2>, <h3>  
2. For each idea/concept:  
   - Explain clearly and thoroughly using the transcription only  
   - Use <span class="emoji"></span> for emojis and <span class="highlight"> for important points  
   - Provide at least 3 real-life examples from diverse contexts to illustrate  
   - Use tables to show contrasts, sequences, or relationships with this structure:
     ```html
     <table>
       <thead>
         <tr>
           <th>Column 1</th>
           <th>Column 2</th>
           <th>Column 3</th>
         </tr>
       </thead>
       <tbody>
         <tr>
           <td>Data 1</td>
           <td>Data 2</td>
           <td>Data 3</td>
         </tr>
       </tbody>
     </table>
     ```
   - If the speaker presents models, theories, or frameworks, include clear tables or structured summaries

Practice & Mastery Section  
3. 5 Conceptual Q&A: Deep, thoughtful questions with clear answers and explanations  
4. 5 Multiple-Choice Questions:  
   - Each with 4 options (A-D)  
   - Indicate the correct answer  
   - Explain why it is correct and why the others are not  
5. 5 Open-Ended Questions:  
   - Encourage reflection, application, or debate  
   - Grounded strictly in the transcription

Language & Context  
- Output must be in the same language as the transcription  
- Accurately reflect any cultural, religious, or philosophical contexts or references—only from the transcription

THINK STEP BY STEP. Be methodical, precise, and insightful.

FINAL INSTRUCTION  
Output only the HTML content that will be placed between the <body> tags. Do not include the HTML template or any other wrapper code.
"""

# ================ Logging Setup ================
def setup_logging() -> logging.Logger:
    """Set up logging configuration with both file and console output."""
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    logger = logging.getLogger('YouTubeTranscriber')
    logger.setLevel(logging.INFO)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    file_handler = logging.FileHandler(f'logs/transcription_{timestamp}.log')
    console_handler = logging.StreamHandler()
    
    log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(log_format)
    console_handler.setFormatter(log_format)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# ================ YouTube Download Functions ================
def is_valid_youtube_url(url: str) -> bool:
    """Validate if the URL is a valid YouTube URL."""
    try:
        parsed = urlparse(url)
        if parsed.netloc not in ['youtube.com', 'www.youtube.com', 'youtu.be']:
            return False
        
        if parsed.netloc == 'youtu.be':
            return bool(parsed.path[1:])
        
        if parsed.path == '/watch':
            query = parse_qs(parsed.query)
            return bool(query.get('v', [''])[0])
        elif '/playlist' in parsed.path:
            query = parse_qs(parsed.query)
            return bool(query.get('list', [''])[0])
        
        return False
    except:
        return False

def download_audio(url: str, output_dir: str, logger: logging.Logger) -> str:
    """Download audio from YouTube URL and return the path to the downloaded file."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Get video ID for consistent naming
    video_id = get_video_id(url)
    output_template = os.path.join(output_dir, f"{video_id}.%(ext)s")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': AUDIO_QUALITY,
        }],
        'outtmpl': output_template,
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Downloading audio from: {url}")
            info = ydl.extract_info(url, download=True)
            if not info:
                raise ValueError("Could not fetch video information")
            
            # Get the downloaded file path
            audio_path = os.path.join(output_dir, f"{video_id}.mp3")
            
            if not os.path.exists(audio_path):
                raise FileNotFoundError("Audio file not found after download")
            
            logger.info(f"Audio downloaded successfully: {audio_path}")
            return audio_path
            
    except Exception as e:
        logger.error(f"Error downloading audio: {e}")
        raise

# ================ Audio Processing Functions ================
def split_audio(audio_path: str, output_dir: str, logger: logging.Logger) -> List[str]:
    """Split audio file into segments and return list of segment paths."""
    logger.info(f"Loading audio file: {audio_path}")
    audio = AudioSegment.from_file(audio_path)
    logger.info(f"Audio duration: {len(audio)/1000:.2f} seconds")
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    step = SEGMENT_LENGTH - SEGMENT_OVERLAP
    segment_files = []
    
    logger.info(f"Splitting audio into {SEGMENT_LENGTH/1000:.1f}s segments with {SEGMENT_OVERLAP/1000:.1f}s overlap")
    
    for i in range(0, len(audio), step):
        segment = audio[i:i + SEGMENT_LENGTH]
        if len(segment) < 1000:  # Skip segments shorter than 1 second
            continue
        
        segment = segment.set_channels(1).set_frame_rate(16000)
        segment_path = os.path.join(output_dir, f"segment_{i//step:04d}.wav")
        segment.export(segment_path, format="wav")
        segment_files.append(segment_path)
        logger.info(f"Saved segment {len(segment_files)}: {i/1000:.1f}s to {(i + len(segment))/1000:.1f}s")
    
    return segment_files

# ================ Transcription Functions ================
def transcribe_segment(model: whisper.Whisper, segment_file: str, logger: logging.Logger) -> Dict:
    """Transcribe a single audio segment using Whisper."""
    logger.info(f"Transcribing file: {segment_file}")
    
    result = model.transcribe(
        segment_file,
        # language="ar",
        task="transcribe",
        verbose=True,
        fp16=False,
        temperature=0.0,
        condition_on_previous_text=False,
        no_speech_threshold=0.6,
        compression_ratio_threshold=2.4,
        logprob_threshold=-1.0,
        word_timestamps=True
    )
    
    logger.info(f"Transcription complete for {segment_file}")
    return result

def save_segment_json(transcription: Dict, output_path: str, segment_num: int, logger: logging.Logger) -> None:
    """Save a single segment transcription to a JSON file."""
    logger.info(f"Saving segment JSON to: {output_path}")
    
    segment_data = {
        "segment_number": segment_num,
        "text": transcription["text"],
        "segments": [
            {
                "start": segment["start"],
                "end": segment["end"],
                "text": segment["text"]
            }
            for segment in transcription.get("segments", [])
        ]
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(segment_data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Segment JSON saved successfully to {output_path}")

def combine_transcriptions(segment_files: List[str], output_path: str, logger: logging.Logger) -> None:
    """Combine all segment JSON files into a single JSON file."""
    logger.info(f"Combining JSON transcriptions to: {output_path}")
    
    combined_data = {"segments": []}
    
    for segment_file in segment_files:
        try:
            with open(segment_file, 'r', encoding='utf-8') as f:
                segment_data = json.load(f)
                combined_data["segments"].append(segment_data)
        except Exception as e:
            logger.error(f"Error loading segment file {segment_file}: {e}")
    
    combined_data["segments"].sort(key=lambda x: x["segment_number"])
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(combined_data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Combined JSON saved successfully to {output_path}")

def extract_text_from_json(json_file_path: str, output_file_path: str, logger: logging.Logger) -> None:
    """Extract text from JSON transcription and save to text file."""
    logger.info(f"Extracting text from JSON: {json_file_path}")
    
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    full_text = []
    for segment in data['segments']:
        if 'text' in segment:
            full_text.append(segment['text'])
    
    combined_text = '\n'.join(full_text)
    
    with open(output_file_path, 'w', encoding='utf-8') as f:
        f.write(combined_text)
    
    logger.info(f"Text extracted and saved to: {output_file_path}")

# ================ LLM Processing Functions ================
def clean_thinking_tags(content: str, logger: logging.Logger) -> str:
    """Remove thinking tags and their content from the LLM response."""
    if not content:
        return content
    
    # Remove <think>...</think> tags and everything between them
    # This handles both single line and multiline thinking blocks
    cleaned_content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove any extra whitespace left by removing thinking blocks
    cleaned_content = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_content)
    cleaned_content = cleaned_content.strip()
    
    # Log if thinking content was found and removed
    if content != cleaned_content:
        thinking_blocks = re.findall(r'<think>.*?</think>', content, flags=re.DOTALL | re.IGNORECASE)
        logger.info(f"Removed {len(thinking_blocks)} thinking block(s) from LLM response")
    
    return cleaned_content

def process_transcription_with_llm(transcription_text: str, prompt_template: str, logger: logging.Logger) -> str:
    """Process the transcription using the local model via OpenAI-compatible API."""
    
    # Replace the placeholder in the prompt with the actual transcription
    full_prompt = prompt_template.replace("[PASTE TRANSCRIPTION HERE]", transcription_text)
    
    logger.info(f"Sending transcription to local model at {LOCAL_MODEL_URL}...")
    
    # Initialize OpenAI client pointing to local model
    client = openai.OpenAI(
        base_url=f"{LOCAL_MODEL_URL}/v1",
        api_key="not-needed"  # Local models typically don't need real API keys
    )
    
    try:
        response = client.chat.completions.create(
            model=LOCAL_MODEL_NAME,
            messages=[
                {
                    "role": "system", 
                    "content": "You are a world-class educator, cognitive scientist, and instructional designer. Follow the instructions precisely and output only the requested structured content."
                },
                {
                    "role": "user", 
                    "content": full_prompt
                }
            ],
            temperature=0.3,
            max_tokens=32768
        )
        
        # Extract the content from the response
        raw_content = response.choices[0].message.content
        
        # Remove thinking tags and their content
        cleaned_content = clean_thinking_tags(raw_content, logger)
        
        # If the content is wrapped in JSON, try to extract the HTML content
        if cleaned_content.startswith('{'):
            try:
                import json
                json_response = json.loads(cleaned_content)
                if 'choices' in json_response and len(json_response['choices']) > 0:
                    if 'message' in json_response['choices'][0]:
                        cleaned_content = json_response['choices'][0]['message']['content']
            except json.JSONDecodeError:
                pass
        
        logger.info("Successfully processed transcription with local model")
        return cleaned_content
        
    except Exception as e:
        logger.error(f"Error calling local model: {e}")
        raise

def generate_html(transcription: str, output_path: str) -> None:
    """Generate an HTML file from the transcription."""
    try:
        # Create HTML content
        html_content = HTML_TEMPLATE.format(
            title="Video Transcription Summary",
            content=transcription
        )
        
        # Save HTML file
        with open(output_path, 'w', encoding='utf-8') as html_file:
            html_file.write(html_content)
        logging.info(f"HTML file saved at: {output_path}")
        
    except Exception as e:
        logging.error(f"Error generating HTML: {str(e)}")
        raise

# ================ Folder Management Functions ================
def get_video_id(url: str) -> str:
    """Extract video ID from YouTube URL."""
    parsed = urlparse(url)
    if parsed.netloc == 'youtu.be':
        return parsed.path[1:]
    query = parse_qs(parsed.query)
    return query.get('v', [''])[0]

def setup_folder_structure(base_dir: str, video_id: str) -> dict:
    """Create and return paths for all required folders."""
    folders = {}
    
    # Create base directory if it doesn't exist
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
    
    # Create video_id directory
    video_dir = os.path.join(base_dir, video_id)
    if not os.path.exists(video_dir):
        os.makedirs(video_dir)
    
    # Create and store paths for each folder type
    for folder_type, folder_name in FOLDER_STRUCTURE.items():
        folder_path = os.path.join(video_dir, folder_name)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        folders[folder_type] = folder_path
    
    return folders

def get_output_paths(folders: dict, video_id: str) -> dict:
    """Generate all output file paths for a video."""
    return {
        'video': os.path.join(folders['video'], f"{video_id}.mp4"),
        'audio': os.path.join(folders['audio'], f"{video_id}.mp3"),
        'segments': [os.path.join(folders['segments'], f"segment_{i:04d}.wav") 
                    for i in range(1000)],  # Assuming max 1000 segments
        'transcriptions': [os.path.join(folders['transcriptions'], f"segment_{i:04d}.json") 
                          for i in range(1000)],
        'full_transcript_json': os.path.join(folders['full_transcriptions'], "transcript.json"),
        'full_transcript_txt': os.path.join(folders['full_transcriptions'], "full_text.txt"),
        'processed_content': os.path.join(folders['processed'], "processed_content.txt"),
        'processed_html': os.path.join(folders['processed'], "processed_content.html")
    }

def is_video_processed(output_paths: dict) -> bool:
    """Check if video has already been fully processed."""
    required_files = [
        output_paths['audio'],
        output_paths['full_transcript_json'],
        output_paths['full_transcript_txt'],
        output_paths['processed_html']
    ]
    return all(os.path.exists(path) for path in required_files)

# ================ Main Processing Function ================
def process_youtube_audio(url: str, output_base_dir: str = DEFAULT_OUTPUT_DIR) -> None:
    """Main function to process YouTube audio: download, transcribe, and generate text."""
    logger = setup_logging()
    
    try:
        # Validate URL
        if not is_valid_youtube_url(url):
            raise ValueError("Invalid YouTube URL provided")
        
        # Get video ID and set up folder structure
        video_id = get_video_id(url)
        folders = setup_folder_structure(output_base_dir, video_id)
        output_paths = get_output_paths(folders, video_id)
        
        # Step 1: Download audio
        logger.info("Step 1: Downloading audio...")
        if not os.path.exists(output_paths['audio']):
            audio_file = download_audio(url, folders['audio'], logger)
            logger.info(f"Audio downloaded and saved to: {output_paths['audio']}")
        else:
            logger.info("Audio file already exists. Using existing file...")
            audio_file = output_paths['audio']
        
        # Step 2: Split audio into segments
        logger.info("\nStep 2: Splitting audio into segments...")
        existing_segments = [f for f in output_paths['segments'] if os.path.exists(f)]
        if not existing_segments:
            segment_files = split_audio(audio_file, folders['segments'], logger)
            logger.info(f"Created {len(segment_files)} audio segments")
        else:
            logger.info(f"Found {len(existing_segments)} existing audio segments. Using them...")
            segment_files = existing_segments
        
        # Step 3: Initialize Whisper model
        logger.info("\nStep 3: Initializing Whisper model...")
        model = whisper.load_model("turbo")
        
        # Step 4: Transcribe segments
        logger.info("\nStep 4: Transcribing segments...")
        segment_json_files = []
        for i, segment_file in enumerate(segment_files):
            transcription_path = output_paths['transcriptions'][i]
            if os.path.exists(transcription_path):
                logger.info(f"Transcription for segment {i + 1} already exists. Using existing transcription...")
                segment_json_files.append(transcription_path)
                continue
                
            logger.info(f"\nProcessing segment {i + 1}/{len(segment_files)}")
            result = transcribe_segment(model, segment_file, logger)
            save_segment_json(result, transcription_path, i + 1, logger)
            segment_json_files.append(transcription_path)
            logger.info(f"Saved transcription for segment {i + 1}")
        
        # Step 5: Combine transcriptions
        logger.info("\nStep 5: Combining transcriptions...")
        if not os.path.exists(output_paths['full_transcript_json']):
            combine_transcriptions(segment_json_files, output_paths['full_transcript_json'], logger)
            logger.info("Created combined transcript JSON")
        else:
            logger.info("Full transcript JSON already exists. Using existing file...")
        
        # Step 6: Generate final text file
        logger.info("\nStep 6: Generating final text file...")
        if not os.path.exists(output_paths['full_transcript_txt']):
            extract_text_from_json(output_paths['full_transcript_json'], output_paths['full_transcript_txt'], logger)
            logger.info("Created full text file")
        else:
            logger.info("Full text file already exists. Using existing file...")
        
        # Step 7: Process transcription with LLM
        logger.info("\nStep 7: Processing transcription with LLM...")
        if not os.path.exists(output_paths['processed_content']):
            prompt_template = PROMPT_TEMPLATE
            
            # Read the transcription text from the file
            with open(output_paths['full_transcript_txt'], 'r', encoding='utf-8') as f:
                transcription_text = f.read()
            
            processed_content = process_transcription_with_llm(transcription_text, prompt_template, logger)
            
            # Save the processed content
            with open(output_paths['processed_content'], 'w', encoding='utf-8') as f:
                f.write(processed_content)
            logger.info("Created processed content file")
        else:
            logger.info("Processed content already exists. Using existing file...")
            with open(output_paths['processed_content'], 'r', encoding='utf-8') as f:
                processed_content = f.read()
        
        # Step 8: Create HTML from processed content
        logger.info("\nStep 8: Creating HTML from processed content...")
        if not os.path.exists(output_paths['processed_html']):
            generate_html(processed_content, output_paths['processed_html'])
            logger.info("Created HTML file")
        else:
            logger.info("HTML file already exists. Using existing file...")
        
        logger.info(f"\nProcessing completed successfully!")
        logger.info(f"Video ID: {video_id}")
        logger.info(f"Audio file: {output_paths['audio']}")
        logger.info(f"Transcript JSON: {output_paths['full_transcript_json']}")
        logger.info(f"Final text file: {output_paths['full_transcript_txt']}")
        logger.info(f"Processed content: {output_paths['processed_content']}")
        logger.info(f"HTML created: {output_paths['processed_html']}")
        
    except Exception as e:
        logger.error(f"Error during processing: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python app.py \"<youtube_url>\"")
        print("Note: Make sure to wrap the URL in quotes!")
        sys.exit(1)
    
    youtube_url = sys.argv[1]
    process_youtube_audio(youtube_url) 