import os
import subprocess
from typing import List, Dict

def format_timestamp(seconds: float) -> str:
    """Format seconds into SRT timestamp format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    # Safety boundary checks
    if millis >= 1000:
        millis = 999
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def create_srt(words: List[Dict], srt_path: str):
    """Create a word-by-word subtitle file in SRT format."""
    print(f"Creating SRT file at: {srt_path}")
    with open(srt_path, "w", encoding="utf-8") as f:
        for idx, w in enumerate(words, 1):
            start_str = format_timestamp(w["start"])
            end_str = format_timestamp(w["end"])
            # Ensure end time is strictly greater than start time
            if w["end"] <= w["start"]:
                end_time = w["start"] + 0.1
                end_str = format_timestamp(end_time)
            
            f.write(f"{idx}\n")
            f.write(f"{start_str} --> {end_str}\n")
            f.write(f"{w['word']}\n\n")

class VideoAssembler:
    @staticmethod
    def assemble(video_path: str, audio_path: str, words: List[Dict], output_path: str) -> str:
        """
        Muxes audio and burns subtitles onto the video using FFmpeg.
        Returns the path of the assembled video.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Source video file not found: {video_path}")
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Source audio file not found: {audio_path}")

        # Determine workspace directory to make paths relative (avoids FFmpeg path issues on Windows)
        workspace_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # Paths relative to the workspace directory
        rel_video = os.path.relpath(video_path, workspace_dir)
        rel_audio = os.path.relpath(audio_path, workspace_dir)
        rel_output = os.path.relpath(output_path, workspace_dir)
        
        # Save SRT file in the same directory as output
        output_dir = os.path.dirname(output_path)
        srt_path = os.path.join(output_dir, "captions.srt")
        create_srt(words, srt_path)
        
        rel_srt = os.path.relpath(srt_path, workspace_dir).replace("\\", "/")

        print(f"Assembling video using FFmpeg...")
        
        # FFmpeg command: mux audio and burn subtitles.
        # We style the subtitles using ForceStyle to make them look premium:
        # Bold, large yellow font with black outline, centered near the lower third.
        subtitle_filter = f"subtitles='{rel_srt}':force_style='Alignment=2,FontSize=20,PrimaryColour=&H00FFFF,OutlineColour=&H000000,BorderStyle=1,Outline=2,Shadow=0,Fontname=Arial,Bold=1'"
        
        cmd = [
            "ffmpeg", "-y",
            "-i", rel_video,
            "-i", rel_audio,
            "-vf", subtitle_filter,
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "fast",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            rel_output
        ]
        
        print(f"Running FFmpeg command:\n{' '.join(cmd)}")
        
        process = subprocess.Popen(
            cmd,
            cwd=workspace_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            print(f"FFmpeg stdout:\n{stdout}")
            print(f"FFmpeg stderr:\n{stderr}")
            raise RuntimeError(f"FFmpeg command failed with exit code {process.returncode}")
            
        print(f"Video assembled successfully: {output_path}")
        return output_path

if __name__ == "__main__":
    # Test assembly
    import json
    test_video = "media/videos/compiled_scene/1080p60/GeneratedShort.mp4" # dummy path for manual test
    test_audio = "test_output/test_eigen.wav"
    test_timestamps = "test_output/test_timestamps.json"
    
    if os.path.exists(test_audio) and os.path.exists(test_timestamps):
        with open(test_timestamps, "r") as f:
            data = json.load(f)
            
        # Create a blank video for testing if it doesn't exist
        if not os.path.exists(test_video):
            print("To test the assembler, rendering the actual video is required first.")
    else:
        print("Test assets are not ready. Please run tts_engine.py and whisper_sync.py first.")
