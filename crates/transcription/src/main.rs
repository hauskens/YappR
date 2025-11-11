use hound::{SampleFormat, WavReader};
use std::path::PathBuf;
use whisper_rs::{FullParams, SamplingStrategy, WhisperContext, WhisperContextParameters};

fn parse_wav_file(path: PathBuf) -> Vec<i16> {
    let reader = WavReader::open(path).expect("failed to read file");

    if reader.spec().channels != 1 {
        panic!("expected mono audio file");
    }
    if reader.spec().sample_format != SampleFormat::Int {
        panic!("expected integer sample format");
    }
    if reader.spec().sample_rate != 16000 {
        panic!("expected 16KHz sample rate");
    }
    if reader.spec().bits_per_sample != 16 {
        panic!("expected 16 bits per sample");
    }

    reader
        .into_samples::<i16>()
        .map(|x| x.expect("sample"))
        .collect::<Vec<_>>()
}

fn main() {
    let path_to_model = std::env::args().nth(1).unwrap();

    let audio_path = PathBuf::from(
        std::env::args()
            .nth(2)
            .expect("second argument should be path to whisper model file"),
    );
    if !audio_path.exists() {
        panic!("audio file doesn't exist");
    }

    // load a context and model
    // https://huggingface.co/ggerganov/whisper.cpp/tree/main
    let ctx = WhisperContext::new_with_params(&path_to_model, WhisperContextParameters::default())
        .expect("failed to load model");

    let original_samples = parse_wav_file(audio_path);

    let mut samples = vec![0.0f32; original_samples.len()];
    whisper_rs::convert_integer_to_float_audio(&original_samples, &mut samples)
        .expect("failed to convert samples");

    let mut state = ctx.create_state().expect("failed to create key");
    let mut params = FullParams::new(SamplingStrategy::BeamSearch {
        beam_size: 5,
        patience: -1.0,
    });
    params.set_initial_prompt("experience");
    params.set_progress_callback_safe(|progress| println!("Progress callback: {}%", progress));

    let st = std::time::Instant::now();
    state
        .full(params, &samples)
        .expect("failed to convert samples");
    let et = std::time::Instant::now();

    for segment in state.as_iter() {
        let start_timestamp = segment.start_timestamp();
        let end_timestamp = segment.end_timestamp();
        println!("[{} - {}]: {}", start_timestamp, end_timestamp, segment);
    }
    println!("took {}ms", (et - st).as_millis());
}
