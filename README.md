# YouTube to HTML Summary Page

An offline tool that converts YouTube videos into structured, educational summaries in HTML format. This tool downloads YouTube videos, transcribes them using OpenAI's Whisper, and processes the content using a local LLM (Ollama) to create comprehensive, well-structured summaries.

## Features

- Downloads YouTube high-quality audio
- Transcribes audio using OpenAI's Whisper model
- Processes transcriptions using local LLM (Ollama) for better privacy and control
- Generates structured HTML summaries with:
  - Clear section headers
  - Highlighted key points
  - Tables for structured information
  - Practice questions and answers
  - Multiple-choice questions
  - Open-ended discussion questions
- Beautiful, responsive HTML output with modern styling
- Supports multiple languages (based on video content)

## Prerequisites

1. Python 3.8 or higher
2. [Ollama](https://ollama.ai/) installed and running locally
3. FFmpeg installed on your system
4. [uv](https://github.com/astral-sh/uv) (recommended for faster installation)

### Installing FFmpeg

- **macOS**:
  ```bash
  brew install ffmpeg
  ```
- **Ubuntu/Debian**:
  ```bash
  sudo apt-get install ffmpeg
  ```
- **Windows**:
  Download from [FFmpeg website](https://ffmpeg.org/download.html)

### Installing Ollama

1. Visit [Ollama's official website](https://ollama.ai/)
2. Download and install Ollama for your operating system
3. Pull the required model:
  ```bash
  ollama pull deepseek-r1:32b
  ```

### Installing uv (Recommended)

uv is a much faster alternative to pip for installing Python packages. It's recommended for this project as it can significantly speed up the installation process.

1. Install uv using one of these methods:

   **Using curl (macOS/Linux)**:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   **Using PowerShell (Windows)**:
   ```powershell
   (Invoke-WebRequest -Uri "https://astral.sh/uv/install.ps1" -UseBasicParsing).Content | pwsh -Command -
   ```

2. Verify installation:
   ```bash
   uv --version
   ```

## Installation

1. Clone the repository:
  ```bash
  git clone https://github.com/mourad-ghafiri/youtube-to-html-summary.git
  cd youtube-to-html-summary
  ```

2. Install the required Python packages:

   Using uv (recommended):
   ```bash
   uv venv
   source .venv/bin/activate
   uv pip install -e .
   ```

   Or using pip:
   ```bash
   pip install -e .
   ```

## Usage

Run the script with a YouTube URL as an argument:

```bash
python main.py "https://www.youtube.com/watch?v=YOUR_VIDEO_ID"
```

Note: Make sure to wrap the URL in quotes!

## Output

The script creates a structured output in the `downloads` directory:

```
downloads/
└── [video_id]/
    ├── audio/              # Downloaded audio file
    ├── segments/           # Audio segments
    ├── transcriptions/     # Individual segment transcriptions
    ├── full_transcriptions/# Combined transcriptions
    └── processed/          # Final processed content
        ├── processed_content.txt
        └── processed_content.html
```

The final output is an HTML file that can be opened in any web browser and printed to PDF if needed.

## Important Notes

1. **Ollama Model**: This project uses the `deepseek-r1:32b` model through Ollama for processing transcriptions. This model provides high-quality output for educational content processing. Make sure you have enough system resources to run this model.

2. **Processing Time**: The processing time depends on:
   - Video length
   - Your system's processing power
   - Internet connection speed
   - Available system resources for the LLM

3. **Storage**: The tool downloads and processes audio files, so ensure you have enough disk space.

## Dependencies

- openai-whisper: For audio transcription
- pydub: For audio processing
- numpy: For numerical operations
- torch: Required for Whisper
- tqdm: For progress bars
- openai: For API compatibility
- yt-dlp: For YouTube video downloading

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Acknowledgments

- OpenAI for the Whisper model
- Ollama for providing the local LLM infrastructure
- The open-source community for various tools and libraries used in this project 