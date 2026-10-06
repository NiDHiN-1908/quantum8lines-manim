import os
import sys
import json
import subprocess
from pathlib import Path

# Add src to python path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from src.pipeline.tts_engine import TTSEngine
from src.pipeline.whisper_sync import WhisperSync
from src.pipeline.generator import ManimCompiler
from src.pipeline.assembler import VideoAssembler
from src.pipeline.qa_validator import QAValidator

def run_pipeline(topic: str, narration_text: str, visual_events: list, output_filename: str):
    print("=" * 60)
    print(f"STARTING PIPELINE FOR TOPIC: {topic}")
    print("=" * 60)
    
    # 1. Setup workspace paths
    output_dir = os.path.join(ROOT_DIR, "test_output")
    os.makedirs(output_dir, exist_ok=True)
    
    script_path = os.path.join(output_dir, "script.json")
    audio_path = os.path.join(output_dir, "narration.wav")
    timestamps_path = os.path.join(output_dir, "timestamps.json")
    manim_script_path = os.path.join(output_dir, "compiled_scene.py")
    assembled_video_path = os.path.join(output_dir, output_filename)
    
    # 2. Write Script JSON contract
    script_data = {
        "meta": {
            "topic": topic,
            "style": "dark_minimalist",
            "aspect_ratio": "9:16"
        },
        "scenes": [
            {
                "scene_id": 1,
                "narration": narration_text,
                "visuals": visual_events
            }
        ]
    }
    
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, indent=2, ensure_ascii=False)
    print(f"Step 1: Script JSON contract written to {script_path}")
    
    # 3. Generate Audio using local TTS
    tts = TTSEngine(voice="af_sarah")
    audio_duration = tts.generate_audio(narration_text, audio_path)
    print(f"Step 2: Narration audio generated. Duration: {audio_duration:.2f}s")
    
    # 4. Extract word timestamps using Whisper
    sync = WhisperSync(model_size="tiny", device="cpu")
    alignment = sync.align(audio_path, timestamps_path)
    print(f"Step 3: Whisper timestamps extracted to {timestamps_path}")
    
    # 5. Compile to Manim Scene python code
    compiler = ManimCompiler(script_path, timestamps_path, audio_path)
    compiler.compile(manim_script_path)
    print(f"Step 4: Compiled Manim scene written to {manim_script_path}")
    
    # 6. Execute Manim render
    # Render in High Quality (1080p60)
    print("Step 5: Executing Manim render (High Quality 1080p60)...")
    manim_cmd = [
        os.path.join(str(ROOT_DIR), ".venv", "Scripts", "manim.exe"), 
        manim_script_path, 
        "GeneratedShort"
    ]
    print(f"Running: {' '.join(manim_cmd)}")
    
    # We run Manim from the root directory to locate imports correctly
    manim_process = subprocess.run(
        manim_cmd,
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    if manim_process.returncode != 0:
        print("Manim Render stdout:\n", manim_process.stdout)
        print("Manim Render stderr:\n", manim_process.stderr)
        raise RuntimeError(f"Manim rendering failed with exit code {manim_process.returncode}")
    print("Manim render completed successfully.")
    
    # Locate raw video path (high quality, 60fps)
    raw_video_path = os.path.join(
        ROOT_DIR, 
        "media", "videos", "compiled_scene", "1080p60", "GeneratedShort.mp4"
    )
    
    if not os.path.exists(raw_video_path):
        # Fallback to check other qualities if config was overridden
        raw_video_path = os.path.join(
            ROOT_DIR, 
            "media", "videos", "compiled_scene", "480p15", "GeneratedShort.mp4"
        )
        if not os.path.exists(raw_video_path):
            raise FileNotFoundError(f"Could not find raw Manim output video file at {raw_video_path}")
            
    print(f"Raw video located at: {raw_video_path}")
    
    # 7. Assemble final video (Mux audio + burn captions)
    print("Step 6: Assembling final captioned video...")
    VideoAssembler.assemble(
        video_path=raw_video_path,
        audio_path=audio_path,
        words=alignment["words"],
        output_path=assembled_video_path
    )
    
    # 8. Run QA validation
    print("Step 7: Executing automated QA validations...")
    qa_report = QAValidator.validate(
        video_path=assembled_video_path,
        audio_path=audio_path,
        timestamps_path=timestamps_path
    )
    
    print("=" * 60)
    print("PIPELINE EXECUTION COMPLETE")
    print(f"Final video: {assembled_video_path}")
    print(f"QA Status: {'SUCCESS' if qa_report['success'] else 'FAILURE'}")
    print("=" * 60)
    
    return qa_report

if __name__ == "__main__":
    # Define our eigenvector concept short
    concept_topic = "Eigenvectors"
    concept_narration = "Eigenvectors do not rotate when a matrix is applied."
    
    concept_visuals = [
        {
            "trigger_word": "eigenvectors",
            "action": "create_vectors",
            "parameters": {}
        },
        {
            "trigger_word": "rotate",
            "action": "highlight_vector",
            "parameters": {}
        },
        {
            "trigger_word": "matrix",
            "action": "apply_matrix",
            "parameters": {
                "matrix": [[2.0, 0.0], [0.6, 0.7]]
            }
        },
        {
            "trigger_word": "applied",
            "action": "show_text",
            "parameters": {
                "text": "This direction doesn't rotate."
            }
        },
        {
            "trigger_word": "applied",
            "action": "fade_out_all",
            "parameters": {}
        }
    ]
    
    run_pipeline(
        topic=concept_topic,
        narration_text=concept_narration,
        visual_events=concept_visuals,
        output_filename="final_eigenvalue_short.mp4"
    )
