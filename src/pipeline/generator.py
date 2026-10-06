import os
import json
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

# -------------------------------------------------------------
# Pydantic Schemas (Strict Contracts)
# -------------------------------------------------------------
class VisualEvent(BaseModel):
    trigger_word: str = Field(..., description="The word in narration that triggers this action")
    action: str = Field(..., description="The type of visual action to perform")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameters for the action")

class SceneSegment(BaseModel):
    scene_id: int
    narration: str
    visuals: List[VisualEvent] = Field(default_factory=list)

class ScriptMeta(BaseModel):
    topic: str
    style: str
    aspect_ratio: str = "9:16"

class ScriptSchema(BaseModel):
    meta: ScriptMeta
    scenes: List[SceneSegment]

class WordTimestamp(BaseModel):
    word: str
    start: float
    end: float

class TimestampsSchema(BaseModel):
    words: List[WordTimestamp]


# -------------------------------------------------------------
# JSON-to-Manim Compiler
# -------------------------------------------------------------
class ManimCompiler:
    def __init__(self, script_path: str, timestamps_path: str, audio_path: str):
        self.script_path = script_path
        self.timestamps_path = timestamps_path
        self.audio_path = audio_path.replace("\\", "/") # Use forward slashes for cross-platform compatibility
        
        # Load and validate files
        with open(script_path, "r", encoding="utf-8") as f:
            self.script_data = ScriptSchema(**json.load(f))
            
        with open(timestamps_path, "r", encoding="utf-8") as f:
            self.timestamps_data = TimestampsSchema(**json.load(f))

    def _clean_word(self, word: str) -> str:
        """Strip punctuation and whitespace for clean matching."""
        return re.sub(r'[^\w\s]', '', word).strip().lower()

    def _find_trigger_time(self, trigger_word: str, segment_words_list: List[WordTimestamp]) -> float:
        """Find the start timestamp of the trigger word within the segment words."""
        cleaned_trigger = self._clean_word(trigger_word)
        for w in segment_words_list:
            if self._clean_word(w.word) == cleaned_trigger:
                return w.start
        
        # Fallback to the first word in the segment if trigger not found
        if segment_words_list:
            print(f"Warning: Trigger word '{trigger_word}' not found in segment. Falling back to start of segment.")
            return segment_words_list[0].start
        return 0.0

    def compile(self, output_py_path: str):
        """Compile script and timestamps into a Manim scene Python file."""
        print(f"Compiling Manim scene to: {output_py_path}")
        
        # Step 1: Align narration words in the script to the whisper timestamps
        timestamp_index = 0
        all_words = self.timestamps_data.words
        
        compiled_events = [] # list of dicts: {"time": float, "action": str, "params": dict, "segment_id": int}
        
        # Process each segment to assign absolute times to visual events
        for segment in self.script_data.scenes:
            # Tokenize segment narration to match words in the absolute timestamp list
            narr_words = [self._clean_word(w) for w in segment.narration.split() if self._clean_word(w)]
            segment_words_timestamps = []
            
            # Match the sequence of words starting from the current index in all_words
            match_count = 0
            for i in range(timestamp_index, len(all_words)):
                if match_count >= len(narr_words):
                    break
                w_info = all_words[i]
                if self._clean_word(w_info.word) == narr_words[match_count]:
                    segment_words_timestamps.append(w_info)
                    match_count += 1
                    timestamp_index = i + 1
            
            # If matching failed to advance, force pointer forward
            if not segment_words_timestamps:
                # Fallback: grab next few words based on narration word count
                segment_words_timestamps = all_words[timestamp_index : timestamp_index + len(narr_words)]
                timestamp_index += len(narr_words)

            # Resolve triggers
            for event in segment.visuals:
                t_trigger = self._find_trigger_time(event.trigger_word, segment_words_timestamps)
                compiled_events.append({
                    "time": t_trigger,
                    "action": event.action,
                    "params": event.parameters,
                    "segment_id": segment.scene_id
                })

        # Sort compiled events by time to ensure sequential animation scheduling
        compiled_events.sort(key=lambda x: x["time"])

        # Step 2: Generate Manim Python code
        code = []
        code.append("# ===== AUTO-GENERATED SCENE CODE (DO NOT EDIT) =====")
        code.append("import sys")
        code.append("from pathlib import Path")
        code.append("ROOT_DIR = Path(__file__).resolve().parents[1]")
        code.append("if str(ROOT_DIR) not in sys.path:")
        code.append("    sys.path.append(str(ROOT_DIR))")
        code.append("")
        code.append("from manim import *")
        code.append("import numpy as np")
        code.append("from src.core.colors import *")
        code.append("from src.core.camera import setup_scene")
        code.append("from src.core.helpers import pause, traced, smooth_shift")
        code.append("")
        code.append("class GeneratedShort(Scene):")
        code.append("    def construct(self):")
        code.append("        setup_scene(self)")
        code.append("")
        code.append("        # 1. Overlay narration sound")
        code.append(f"        self.add_sound(r'{self.audio_path}')")
        code.append("")
        code.append("        # 2. Object storage")
        code.append("        vectors = VGroup()")
        code.append("        eigen_vector = None")
        code.append("        sentence = None")
        code.append("        grid = None")
        code.append("")
        code.append("        # 3. Timeline animation sequence")
        
        t_timeline = 0.0
        
        for event in compiled_events:
            t_trigger = event["time"]
            action = event["action"]
            params = event["params"]
            
            # Align timeline to trigger time
            if t_timeline < t_trigger:
                wait_time = round(t_trigger - t_timeline, 3)
                code.append(f"        self.wait({wait_time})")
                t_timeline = t_trigger
                
            code.append(f"        # Event: {action} (Segment {event['segment_id']}, Time {t_trigger}s)")
            
            # Generate code depending on the visual action
            if action == "create_vectors":
                code.append("        # Create base vector set")
                code.append("        directions = [")
                code.append("            np.array([1.0, 0.0, 0]),")
                code.append("            np.array([0.6, 0.8, 0]),")
                code.append("            np.array([-0.7, 0.5, 0]),")
                code.append("            np.array([-0.4, -0.9, 0]),")
                code.append("            np.array([0.3, -0.6, 0]),")
                code.append("        ]")
                code.append("        for d in directions:")
                code.append("            v = Arrow(ORIGIN, 2.5 * d, buff=0, stroke_width=4, color=STATIC)")
                code.append("            vectors.add(v)")
                code.append("        self.play(FadeIn(vectors), run_time=1.0)")
                t_timeline += 1.0
                
            elif action == "highlight_vector":
                code.append("        # Highlight the eigenvector")
                code.append("        eigen_vector = Arrow(ORIGIN, 2.5 * np.array([1, 0, 0]), buff=0, stroke_width=6, color=PRIMARY)")
                code.append("        self.play(ReplacementTransform(vectors[0], eigen_vector), run_time=0.8)")
                # Update vectors vgroup to replace first item
                code.append("        vectors.remove(vectors[0])")
                code.append("        vectors.add(eigen_vector)")
                t_timeline += 0.8
                
            elif action == "apply_matrix":
                matrix = params.get("matrix", [[2.0, 0.0], [0.6, 0.7]])
                code.append(f"        # Apply linear transformation matrix: {matrix}")
                code.append(f"        transform_matrix = np.array({matrix})")
                # Also animate grid for better visual context
                code.append("        grid = NumberPlane(background_line_style={'stroke_opacity': 0.2})")
                code.append("        self.add(grid)")
                code.append("        self.play(ApplyMatrix(transform_matrix, vectors), ApplyMatrix(transform_matrix, grid), run_time=2.2)")
                t_timeline += 2.2
                
            elif action == "show_text":
                text_str = params.get("text", "This direction does not rotate.")
                code.append(f"        # Show text: '{text_str}'")
                code.append(f'        sentence = Text("""{text_str}""", font_size=32, color=HIGHLIGHT).to_edge(DOWN)')
                code.append("        self.play(Write(sentence), run_time=1.2)")
                t_timeline += 1.2
                
            elif action == "fade_out_all":
                code.append("        # Fade out everything")
                code.append("        self.play(FadeOut(vectors), FadeOut(sentence), FadeOut(grid) if grid else Wait(0.1), run_time=1.0)")
                t_timeline += 1.0
                
            code.append("")
            
        # Add buffer wait at the end to match total audio duration
        # Check audio length from soundfile to make sure video duration aligns
        import soundfile as sf
        total_audio_duration = 0.0
        try:
            with sf.SoundFile(self.audio_path) as audio_file:
                total_audio_duration = len(audio_file) / audio_file.samplerate
        except Exception:
            total_audio_duration = t_timeline + 2.0  # fallback
            
        if t_timeline < total_audio_duration:
            rem_wait = round(total_audio_duration - t_timeline, 3)
            code.append(f"        # Wait for audio to finish")
            code.append(f"        self.wait({rem_wait})")
            
        os.makedirs(os.path.dirname(output_py_path), exist_ok=True)
        with open(output_py_path, "w", encoding="utf-8") as f:
            f.write("\n".join(code))
        print("Compilation complete.")

if __name__ == "__main__":
    # Test compilation
    # Write sample files for test run
    os.makedirs("test_output", exist_ok=True)
    
    sample_script = {
      "meta": {
        "topic": "Eigenvalues",
        "style": "dark_minimalist",
        "aspect_ratio": "9:16"
      },
      "scenes": [
        {
          "scene_id": 1,
          "narration": "Eigenvectors do not rotate when a matrix is applied.",
          "visuals": [
            {"trigger_word": "eigenvectors", "action": "create_vectors", "parameters": {}},
            {"trigger_word": "rotate", "action": "highlight_vector", "parameters": {}},
            {"trigger_word": "matrix", "action": "apply_matrix", "parameters": {"matrix": [[2.0, 0.0], [0.6, 0.7] ]}},
            {"trigger_word": "applied", "action": "show_text", "parameters": {"text": "This direction doesn't rotate."}}
          ]
        }
      ]
    }
    
    with open("test_output/test_script.json", "w") as f:
        json.dump(sample_script, f, indent=2)
        
    # Compile
    if os.path.exists("test_output/test_timestamps.json") and os.path.exists("test_output/test_eigen.wav"):
        compiler = ManimCompiler(
            "test_output/test_script.json",
            "test_output/test_timestamps.json",
            "test_output/test_eigen.wav"
        )
        compiler.compile("test_output/compiled_scene.py")
    else:
        print("Sample files not ready. Run tts_engine.py and whisper_sync.py first.")
