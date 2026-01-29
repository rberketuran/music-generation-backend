import sys
from pathlib import Path

# Add parent directory to path to import models
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))
from models import MusicGenerationRequest


def format_composition_plan(request: MusicGenerationRequest) -> dict:
    """
    Format user preferences into ElevenLabs composition plan format.
    
    Args:
        request: MusicGenerationRequest with user preferences
        
    Returns:
        dict: Formatted composition plan matching ElevenLabs API format
    """
    # Parse style text into list (split by comma and strip whitespace)
    positive_local_styles = [
        style.strip() 
        for style in request.style.split(',') 
        if style.strip()
    ]
    
    # Build negative_local_styles
    negative_local_styles = []
    if request.is_instrumental:
        negative_local_styles.append("no vocals")
    
    # Build lines array (always use lyrics when not instrumental)
    lines = []
    if not request.is_instrumental and request.lyrics:
        # Split lyrics by line breaks or use as single line
        lines = [line.strip() for line in request.lyrics.split('\n') if line.strip()]
        if not lines:
            lines = [request.lyrics.strip()]
    
    # Convert duration from seconds to milliseconds
    duration_ms = request.duration_seconds * 1000
    
    # Build positive_global_styles
    positive_global_styles = []
    if not request.is_instrumental and request.vocal_gender:
        positive_global_styles.append(f"{request.vocal_gender} vocal")
    
    # Build composition plan
    composition_plan = {
        "sections": [
            {
                "section_name": "Main Theme",
                "duration_ms": duration_ms,
                "lines": lines,
                "positive_local_styles": positive_local_styles,
                "negative_local_styles": negative_local_styles
            }
        ],
        "positive_global_styles": positive_global_styles,
        "negative_global_styles": []
    }
    
    return composition_plan
