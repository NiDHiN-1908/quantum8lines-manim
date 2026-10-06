import os
import time
import urllib.request
import soundfile as sf
from kokoro_onnx import Kokoro

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models")
MODEL_PATH = os.path.join(MODEL_DIR, "kokoro-v1.0.int8.onnx")
VOICES_PATH = os.path.join(MODEL_DIR, "voices-v1.0.bin")

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

def download_file(url: str, dest_path: str, retries: int = 5):
    """Download a file in chunks with retries, file-size verification, and temp files."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    temp_path = dest_path + ".tmp"
    
    for attempt in range(1, retries + 1):
        try:
            print(f"Downloading {url} to {dest_path} (Attempt {attempt}/{retries})...")
            
            # Use headers to look like a standard client to prevent blockages
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            
            with urllib.request.urlopen(req) as response, open(temp_path, "wb") as out_file:
                total_size = int(response.info().get('Content-Length', 0))
                downloaded = 0
                block_size = 65536  # 64KB blocks for speed
                
                last_percent = -1
                while True:
                    buffer = response.read(block_size)
                    if not buffer:
                        break
                    out_file.write(buffer)
                    downloaded += len(buffer)
                    
                    if total_size > 0:
                        percent = (downloaded * 100) // total_size
                        # Print progress updates in 10% steps
                        if percent % 10 == 0 and percent != last_percent:
                            print(f"Progress: {percent}% ({downloaded}/{total_size} bytes)...", end="\r")
                            last_percent = percent
                
            # Verify file size matches expected size
            if total_size > 0 and os.path.getsize(temp_path) != total_size:
                raise IOError(f"File size mismatch: got {os.path.getsize(temp_path)} bytes, expected {total_size} bytes")
                
            if os.path.exists(dest_path):
                os.remove(dest_path)
            os.rename(temp_path, dest_path)
            print(f"\nDownload complete: {os.path.basename(dest_path)}")
            return
            
        except Exception as e:
            print(f"\nAttempt {attempt} failed with error: {e}")
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            if attempt < retries:
                print("Waiting 3 seconds before retrying...")
                time.sleep(3)
            else:
                raise IOError(f"Failed to download {url} after {retries} attempts.")

def ensure_models_downloaded():
    """Ensure the ONNX model and voices binary are downloaded."""
    if not os.path.exists(MODEL_PATH):
        download_file(MODEL_URL, MODEL_PATH)
    if not os.path.exists(VOICES_PATH):
        download_file(VOICES_URL, VOICES_PATH)

class TTSEngine:
    def __init__(self, voice: str = "af_sarah"):
        ensure_models_downloaded()
        print("Initializing Kokoro TTS engine...")
        self.kokoro = Kokoro(MODEL_PATH, VOICES_PATH)
        self.default_voice = voice

    def generate_audio(self, text: str, output_path: str, voice: str = None) -> float:
        """
        Generate a wav audio file from text.
        Returns the duration of the generated audio in seconds.
        """
        voice = voice or self.default_voice
        print(f"Generating audio for: '{text[:40]}...' using voice '{voice}'")
        
        samples, sample_rate = self.kokoro.create(
            text,
            voice=voice,
            speed=1.0,
            lang="en-us"
        )
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        sf.write(output_path, samples, sample_rate)
        
        duration = len(samples) / sample_rate
        print(f"Audio saved to {output_path} (Duration: {duration:.2f}s)")
        return duration

if __name__ == "__main__":
    # Test execution
    engine = TTSEngine()
    duration = engine.generate_audio("Eigenvectors do not rotate when a matrix is applied.", "test_output/test_eigen.wav")
    print(f"Test complete. Duration: {duration:.2f}s")
