"""
Simple test script to verify the composition plan formatting matches expected format.
Run this from the backend directory: python test_formatting.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from models import MusicGenerationRequest
from services.elevenlabs_service import format_composition_plan
import json

def test_instrumental():
    """Test instrumental music generation"""
    print("Test 1: Instrumental Music")
    request = MusicGenerationRequest(
        is_instrumental=True,
        style="50s soul, saxophone, drums",
        duration_seconds=30
    )
    result = format_composition_plan(request)
    print(json.dumps(result, indent=2))
    assert "no vocals" in result["sections"][0]["negative_local_styles"]
    assert result["sections"][0]["lines"] == []
    assert result["positive_global_styles"] == []  # Should be empty for instrumental
    print("[PASS] Instrumental test passed\n")

def test_non_instrumental_with_lyrics():
    """Test non-instrumental music with lyrics"""
    print("Test 2: Non-Instrumental with Lyrics")
    request = MusicGenerationRequest(
        is_instrumental=False,
        lyrics="I will conquer!",
        style="intense, fast-paced electronic, driving synth arpeggios",
        duration_seconds=10
    )
    result = format_composition_plan(request)
    print(json.dumps(result, indent=2))
    assert result["sections"][0]["lines"] == ["I will conquer!"]
    assert "no vocals" not in result["sections"][0]["negative_local_styles"]
    assert "vocals" in result["positive_global_styles"]  # Should include vocals
    print("[PASS] Non-instrumental with lyrics test passed\n")

def test_non_instrumental_multiple_styles():
    """Test non-instrumental with multiple styles and lyrics"""
    print("Test 3: Non-Instrumental with Multiple Styles")
    request = MusicGenerationRequest(
        is_instrumental=False,
        lyrics="I will conquer!",
        style="intense, fast-paced electronic, driving synth arpeggios, punchy drums, distorted bass",
        duration_seconds=10
    )
    result = format_composition_plan(request)
    print(json.dumps(result, indent=2))
    assert result["sections"][0]["lines"] == ["I will conquer!"]
    assert result["sections"][0]["duration_ms"] == 10000
    assert len(result["sections"][0]["positive_local_styles"]) == 5
    assert "vocals" in result["positive_global_styles"]  # Should include vocals
    print("[PASS] Non-instrumental with multiple styles test passed\n")

def test_format_structure():
    """Verify the structure matches ElevenLabs expected format"""
    print("Test 4: Format Structure Verification")
    request = MusicGenerationRequest(
        is_instrumental=False,
        lyrics="I will conquer!",
        style="intense, fast-paced electronic, driving synth arpeggios",
        duration_seconds=10
    )
    result = format_composition_plan(request)
    
    # Verify structure
    assert "sections" in result
    assert len(result["sections"]) == 1
    section = result["sections"][0]
    assert "section_name" in section
    assert "duration_ms" in section
    assert "lines" in section
    assert "positive_local_styles" in section
    assert "negative_local_styles" in section
    assert "positive_global_styles" in result
    assert "negative_global_styles" in result
    
    print("Expected structure:")
    expected = {
        "sections": [{
            "section_name": "Main Theme",
            "duration_ms": 10000,
            "lines": ["I will conquer!"],
            "positive_local_styles": ["intense", "fast-paced electronic", "driving synth arpeggios"],
            "negative_local_styles": []
        }],
        "positive_global_styles": ["vocals"],  # Should include vocals for non-instrumental
        "negative_global_styles": []
    }
    print(json.dumps(expected, indent=2))
    print("\nActual structure:")
    print(json.dumps(result, indent=2))
    print("[PASS] Format structure test passed\n")

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Composition Plan Formatting")
    print("=" * 60 + "\n")
    
    try:
        test_instrumental()
        test_non_instrumental_with_lyrics()
        test_non_instrumental_multiple_styles()
        test_format_structure()
        print("=" * 60)
        print("All tests passed! [SUCCESS]")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
