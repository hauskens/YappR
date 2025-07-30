import json
import time
from pydantic import BaseModel
from .models.config import config
from app.logger import logger


def transcribe(path: str) -> str:
    import whisperx  # type: ignore
    device = config.transcription_device  # cuda
    batch_size = config.transcription_batch_size  # reduce if low on GPU mem
    compute_type = config.transcription_compute_type
    load_model = config.transcription_model

    logger.info("Got path: %s, starting to transcribe with model %s, device %s, compute type %s, batch size %s",
                path, load_model, device, compute_type, batch_size)
    model_dir = f"{config.cache_location}/models/"
    model = whisperx.load_model(
        load_model,
        device,
        compute_type=compute_type,
        download_root=model_dir,
        language="en",
    )

    audio = whisperx.load_audio(path)
    result = model.transcribe(
        audio, batch_size=batch_size, chunk_size=10, language="en")

    # delete model if low on GPU resources
    # import gc; gc.collect(); torch.cuda.empty_cache(); del model

    # # 2. Align whisper output
    # model_a, metadata = whisperx.load_align_model(
    #     language_code=result["language"], device=device
    # )
    # result = whisperx.align(
    #     result["segments"],
    #     model_a,
    #     metadata,
    #     audio,
    #     device,
    #     return_char_alignments=False,
    # )
    #
    # # delete model if low on GPU resources
    # # import gc; gc.collect(); torch.cuda.empty_cache(); del model_a
    #
    # # 3. Assign speaker labels
    # if config.hf_token:
    #     diarize_model = whisperx.diarize.DiarizationPipeline(
    #         use_auth_token=config.hf_token, device=device
    #     )
    #     diarize_segments = diarize_model(audio)
    #     result = whisperx.assign_word_speakers(diarize_segments, result)

    # # add min/max number of speakers if known
    # diarize_segments = diarize_model(audio)
    # # diarize_model(audio, min_speakers=min_speakers, max_speakers=max_speakers)
    #
    # result = whisperx.assign_word_speakers(diarize_segments, result)
    # print(diarize_segments)
    # print(result["segments"])  # segments are now assigned speaker IDs

    # write result to file and return file path, remove origirnal file extension
    filename = f"{path.split(".")[0]}.json"
    with open(filename, "w") as f:
        _ = f.write(json.dumps(result))

    return filename


class TranscriptionMetrics(BaseModel):
    """Metrics for a completed transcription task."""
    audio_duration: float  # Duration of audio in seconds
    transcription_time: float  # Time taken to transcribe in seconds
    timestamp: float  # When this was recorded


class TranscriptionProgressTracker:
    """Manages transcription progress estimation using historical data."""
    
    METRICS_KEY = "transcription_metrics"
    PROGRESS_KEY_PREFIX = "transcription_progress:"
    MAX_STORED_METRICS = 10
    
    def __init__(self):
        from app.redis_client import RedisTaskQueue
        self.redis_client = RedisTaskQueue().redis_client
    
    def store_completion_metrics(self, audio_duration: float, transcription_time: float):
        """Store completion metrics for a transcription task."""
        try:
            metrics = TranscriptionMetrics(
                audio_duration=audio_duration,
                transcription_time=transcription_time,
                timestamp=time.time()
            )
            
            # Get existing metrics
            existing_data = self.redis_client.get(self.METRICS_KEY)
            metrics_list = []
            
            if existing_data:
                metrics_list = json.loads(existing_data)
            
            # Add new metrics
            metrics_list.append(metrics.dict())
            
            # Keep only the latest MAX_STORED_METRICS entries
            if len(metrics_list) > self.MAX_STORED_METRICS:
                metrics_list = metrics_list[-self.MAX_STORED_METRICS:]
            
            # Store back to Redis with 30-day expiration
            self.redis_client.setex(self.METRICS_KEY, 30 * 24 * 60 * 60, json.dumps(metrics_list))
            
            logger.info("Stored transcription metrics: %.1fs audio took %.1fs to transcribe", 
                       audio_duration, transcription_time)
                       
        except Exception as e:
            logger.error("Failed to store transcription metrics: %s", e)
    
    def get_estimated_duration(self, audio_duration: float) -> float | None:
        """Get estimated transcription time based on historical data."""
        try:
            existing_data = self.redis_client.get(self.METRICS_KEY)
            if not existing_data:
                # No historical data, use rough estimate (real-time factor of 0.1)
                return audio_duration * 0.1
            
            metrics_list = json.loads(existing_data)
            if not metrics_list:
                return audio_duration * 0.1
            
            # Calculate average transcription speed (transcription_time / audio_duration)
            total_ratio = 0
            count = 0
            
            for metrics_data in metrics_list:
                if metrics_data['audio_duration'] > 0:
                    ratio = metrics_data['transcription_time'] / metrics_data['audio_duration']
                    total_ratio += ratio
                    count += 1
            
            if count == 0:
                return audio_duration * 0.1
            
            average_ratio = total_ratio / count
            estimated_time = audio_duration * average_ratio
            
            logger.debug("Estimated transcription time: %.1fs (based on %d samples, avg ratio %.3f)", 
                        estimated_time, count, average_ratio)
            
            return estimated_time
            
        except Exception as e:
            logger.error("Failed to get estimated duration: %s", e)
            return audio_duration * 0.1  # Fallback estimate
    
    def start_progress_tracking(self, task_id: str, audio_duration: float):
        """Start tracking progress for a transcription task."""
        try:
            estimated_duration = self.get_estimated_duration(audio_duration)
            
            progress_data = {
                'start_time': time.time(),
                'audio_duration': audio_duration,
                'estimated_duration': estimated_duration
            }
            
            # Store progress data with 1-hour expiration
            key = f"{self.PROGRESS_KEY_PREFIX}{task_id}"
            self.redis_client.setex(key, 3600, json.dumps(progress_data))
            
            logger.info("Started progress tracking for task %s: %.1fs audio, estimated %.1fs transcription", 
                       task_id, audio_duration, estimated_duration)
                       
        except Exception as e:
            logger.error("Failed to start progress tracking for task %s: %s", task_id, e)
    
    def get_progress_estimate(self, task_id: str) -> dict | None:
        """Get current progress estimate for a transcription task."""
        try:
            key = f"{self.PROGRESS_KEY_PREFIX}{task_id}"
            progress_data = self.redis_client.get(key)
            
            if not progress_data:
                return None
            
            data = json.loads(progress_data)
            current_time = time.time()
            elapsed_time = current_time - data['start_time']
            estimated_duration = data['estimated_duration']
            
            # Calculate progress percentage
            if estimated_duration > 0:
                progress_percent = min(95, int((elapsed_time / estimated_duration) * 100))
            else:
                progress_percent = 0
            
            # Calculate ETA
            if progress_percent > 0 and progress_percent < 95:
                remaining_time = estimated_duration - elapsed_time
                eta = max(0, int(remaining_time))
            else:
                eta = 0
            
            return {
                'percent': progress_percent,
                'elapsed_time': elapsed_time,
                'estimated_total': estimated_duration,
                'eta': eta,
                'status': f'Transcribing audio... {progress_percent}%'
            }
            
        except Exception as e:
            logger.error("Failed to get progress estimate for task %s: %s", task_id, e)
            return None
    
    def cleanup_progress_tracking(self, task_id: str):
        """Clean up progress tracking data for a completed task."""
        try:
            key = f"{self.PROGRESS_KEY_PREFIX}{task_id}"
            self.redis_client.delete(key)
        except Exception as e:
            logger.error("Failed to cleanup progress tracking for task %s: %s", task_id, e)


# Global instance
transcription_tracker = TranscriptionProgressTracker()
