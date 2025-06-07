import json
from .models.config import config
from app.logger import logger


def transcribe(path: str) -> str:
    import whisperx
    device = config.transcription_device  # cuda
    batch_size = config.transcription_batch_size  # reduce if low on GPU mem
    compute_type = config.transcription_compute_type
    load_model = config.transcription_model

    logger.info("Got path: %s, starting to transcribe with model %s, device %s, compute type %s, batch size %s", path, load_model, device, compute_type, batch_size)
    model_dir = f"{config.cache_location}/models/"
    model = whisperx.load_model(
        load_model,
        device,
        compute_type=compute_type,
        download_root=model_dir,
        language="en",
    )

    audio = whisperx.load_audio(path)
    result = model.transcribe(audio, batch_size=batch_size, chunk_size=10, language="en")

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