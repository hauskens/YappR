def convert_to_srt(data):
    """Convert transcription data to SRT format.
    
    Args:
        data: Either a JSON object with 'segments' key or a list of segment objects
            Each segment should have 'start', 'end', and 'text' attributes/keys
    
    Returns:
        str: The transcription in SRT format
    """
    # Convert to SRT format
    srt_content = []
    
    # Handle both JSON data with segments key and direct list of segments
    if isinstance(data, dict) and 'segments' in data:
        segments = data.get('segments', [])
    elif isinstance(data, list):
        segments = data
    else:
        segments = []
    
    for i, segment in enumerate(segments, 1):
        # Handle both dict access and object attribute access
        if isinstance(segment, dict):
            start = segment.get('start', 0)
            end = segment.get('end', 0)
            text = segment.get('text', '')
        else:
            # Assume object with attributes
            start = getattr(segment, 'start', 0)
            end = getattr(segment, 'end', 0)
            text = getattr(segment, 'text', '')
            
        # Format timestamps as HH:MM:SS,mmm
        start_time = format_timestamp(start)
        end_time = format_timestamp(end)
            
        # Add entry to SRT content
        srt_content.append(f"{i}\n{start_time} --> {end_time}\n{text}\n")
    
    srt_text = "\n".join(srt_content)
    return srt_text

# Helper function to format timestamp for SRT
def format_timestamp(seconds):
    """
    Format seconds to SRT timestamp format (HH:MM:SS,mmm).
    
    Args:
        seconds: Time in seconds (can be a float)
            
    Returns:
        str: Formatted timestamp
    """
    # Convert to string with 3 decimal places and parse manually to avoid rounding errors
    time_str = f"{seconds:.3f}"
    whole, frac = time_str.split('.')
    
    milliseconds = frac
    
    total_seconds = int(whole)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds}"