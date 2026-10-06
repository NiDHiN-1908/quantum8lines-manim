import os
import subprocess
import json
import soundfile as sf

class QAValidator:
    @staticmethod
    def get_video_duration(video_path: str) -> float:
        """Query video file duration using ffprobe."""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr}")
        return float(result.stdout.strip())

    @staticmethod
    def validate(video_path: str, audio_path: str, timestamps_path: str, tolerance: float = 0.5) -> dict:
        """
        Run local automated QA validations.
        Checks:
          1. File existence
          2. Non-zero size
          3. Duration matching (video vs audio) within tolerance
          4. Subtitle completeness
        """
        report = {
            "success": True,
            "errors": [],
            "warnings": [],
            "metrics": {}
        }

        # 1. Existence and Size checks
        if not os.path.exists(video_path):
            report["success"] = False
            report["errors"].append(f"Assembled video file does not exist: {video_path}")
            return report

        video_size = os.path.getsize(video_path)
        report["metrics"]["video_size_bytes"] = video_size
        if video_size == 0:
            report["success"] = False
            report["errors"].append("Assembled video file is empty (0 bytes).")
            return report

        # 2. Audio existence and check
        if not os.path.exists(audio_path):
            report["success"] = False
            report["errors"].append(f"Audio file does not exist: {audio_path}")
            return report

        # 3. Duration alignment check (Video vs Audio)
        try:
            video_dur = QAValidator.get_video_duration(video_path)
            report["metrics"]["video_duration_seconds"] = round(video_dur, 3)
            
            with sf.SoundFile(audio_path) as audio_file:
                audio_dur = len(audio_file) / audio_file.samplerate
            report["metrics"]["audio_duration_seconds"] = round(audio_dur, 3)

            delta = abs(video_dur - audio_dur)
            report["metrics"]["duration_delta_seconds"] = round(delta, 3)

            if delta > tolerance:
                report["success"] = False
                report["errors"].append(
                    f"Duration mismatch: Video ({video_dur:.2f}s) and Audio ({audio_dur:.2f}s) "
                    f"differ by {delta:.2f}s (tolerance: {tolerance}s)"
                )
        except Exception as e:
            report["success"] = False
            report["errors"].append(f"Failed during duration validation: {e}")

        # 4. SRT validation (completeness)
        srt_path = os.path.join(os.path.dirname(video_path), "captions.srt")
        if os.path.exists(srt_path):
            try:
                with open(srt_path, "r", encoding="utf-8") as f:
                    srt_content = f.read()
                
                with open(timestamps_path, "r", encoding="utf-8") as f:
                    timestamp_data = json.load(f)
                
                words = [w["word"] for w in timestamp_data.get("words", [])]
                missing_words = []
                for w in words:
                    # Basic check if word exists in SRT
                    if w not in srt_content:
                        missing_words.append(w)
                
                report["metrics"]["total_words"] = len(words)
                report["metrics"]["missing_words_count"] = len(missing_words)
                
                if missing_words:
                    report["warnings"].append(
                        f"Some script words ({len(missing_words)}) were not matched in subtitles: {missing_words[:5]}..."
                    )
            except Exception as e:
                report["warnings"].append(f"Subtitles completeness check failed: {e}")
        else:
            report["warnings"].append(f"SRT file not found for validation: {srt_path}")

        print(f"QA Validation complete. Result: {'SUCCESS' if report['success'] else 'FAILURE'}")
        if report["errors"]:
            print("Errors:")
            for err in report["errors"]:
                print(f"  - {err}")
        if report["warnings"]:
            print("Warnings:")
            for warn in report["warnings"]:
                print(f"  - {warn}")

        return report

if __name__ == "__main__":
    # Test validator
    # Can only test if actual video exists
    print("QA Validator module compiled.")
