import whisperx
import logging

from whisperx.types import TranscriptionResult
from .models.config import config


logger = logging.getLogger(__name__)


def transcribe(path: str) -> TranscriptionResult:
    logger.info(f"Got path: {path}")
    device = config.transcription_device  # cuda
    batch_size = config.transcription_batch_size  # reduce if low on GPU mem
    compute_type = config.transcription_compute_type
    load_model = config.transcription_model

    model_dir = f"{config.cache_location}/models/"
    model = whisperx.load_model(
        load_model,
        device,
        compute_type=compute_type,
        download_root=model_dir,
        language="en",
    )

    audio = whisperx.load_audio(path)
    return model.transcribe(audio, batch_size=batch_size, chunk_size=10, language="en")

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
    # print(result["segments"])  # after alignment
    #
    # # delete model if low on GPU resources
    # # import gc; gc.collect(); torch.cuda.empty_cache(); del model_a
    #
    # # 3. Assign speaker labels
    # diarize_model = whisperx.DiarizationPipeline(
    #     use_auth_token=YOUR_HF_TOKEN, device=device
    # )
    #
    # # add min/max number of speakers if known
    # diarize_segments = diarize_model(audio)
    # # diarize_model(audio, min_speakers=min_speakers, max_speakers=max_speakers)
    #
    # result = whisperx.assign_word_speakers(diarize_segments, result)
    # print(diarize_segments)
    # print(result["segments"])  # segments are now assigned speaker IDs
