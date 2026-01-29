from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from models import (
    MusicGenerationRequest, GenerateMusicResponse, StatusResponse, CreditsResponse,
    VoiceConversionResponse, VoiceConversionStatusResponse
)
from services.elevenlabs_service import format_composition_plan
from services.elevenlabs_client import ElevenLabsClient
from services.rvc_client import RVCClient
from datetime import datetime
import uuid
import io
import logging
import tempfile
import os
import aiofiles
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="ElevenLabs Music Generator API")

# Initialize ElevenLabs client
try:
    elevenlabs_client = ElevenLabsClient()
except Exception as e:
    print(f"Warning: Failed to initialize ElevenLabs client: {e}")
    elevenlabs_client = None

# Initialize RVC client
try:
    rvc_client = RVCClient()
except Exception as e:
    logger.warning(f"Failed to initialize RVC client: {e}")
    rvc_client = None

# In-memory task storage
tasks = {}  # {task_id: {status, created_at, composition_plan, ...}}
voice_conversion_jobs = {}  # {job_id: {status, created_at, file_paths, ...}}

# Configure CORS for frontend
# Support both local development and production frontend URLs
cors_origins = [
    "http://localhost:5173",  # Vite default port
    "http://localhost:3000",  # Alternative local port
]

# Add production frontend URL from environment if set
frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    cors_origins.append(frontend_url)

# Allow all origins in development, or specific origins in production
allow_all_origins = os.getenv("ALLOW_ALL_ORIGINS", "false").lower() == "true"
if allow_all_origins:
    cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "ElevenLabs Music Generator API"}


@app.post("/api/generate", response_model=GenerateMusicResponse)
async def generate_music(request: MusicGenerationRequest):
    """
    Generate music composition by submitting to ElevenLabs API.
    Returns task_id for status polling.
    """
    if not elevenlabs_client:
        raise HTTPException(
            status_code=500, 
            detail="ElevenLabs client not initialized. Check API key configuration."
        )
    
    try:
        # Format composition plan
        composition_plan = format_composition_plan(request)
        
        # Submit to ElevenLabs API
        response = elevenlabs_client.compose_detailed(composition_plan)
        
        # Extract task_id from response
        # The response structure may vary - adjust based on actual SDK response
        task_id = None
        
        # Check for task_id in various possible locations
        if hasattr(response, 'task_id'):
            task_id = response.task_id
        elif hasattr(response, 'id'):
            task_id = response.id
        elif isinstance(response, dict):
            task_id = response.get('task_id') or response.get('id')
        
        # Check if audio is directly in response (synchronous completion)
        has_audio = False
        if hasattr(response, 'audio') and response.audio:
            has_audio = True
        elif isinstance(response, dict) and response.get('audio'):
            has_audio = True
        
        # If audio is directly available, mark as completed immediately
        if has_audio and not task_id:
            task_id = str(uuid.uuid4())
            tasks[task_id] = {
                'status': 'completed',
                'created_at': datetime.now(),
                'composition_plan': composition_plan,
                'response': response
            }
            return GenerateMusicResponse(
                task_id=task_id,
                status='completed',
                message='Music generation completed'
            )
        
        # If no task_id and no audio, generate task_id for tracking
        if not task_id:
            task_id = str(uuid.uuid4())
        
        # Store task info
        tasks[task_id] = {
            'status': 'pending',
            'created_at': datetime.now(),
            'composition_plan': composition_plan,
            'response': response
        }
        
        return GenerateMusicResponse(
            task_id=task_id,
            status='pending',
            message='Music generation started'
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/status/{task_id}", response_model=StatusResponse)
async def get_status(task_id: str):
    """
    Get status of a music generation task.
    Polls ElevenLabs API if task is still pending/processing.
    """
    if not elevenlabs_client:
        raise HTTPException(
            status_code=500,
            detail="ElevenLabs client not initialized"
        )
    
    # Check if task exists in local storage
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = tasks[task_id]
    current_status = task.get('status', 'pending')
    
    # If already completed or failed, return stored status
    if current_status in ['completed', 'failed']:
        return StatusResponse(
            task_id=task_id,
            status=current_status,
            message=task.get('message', '')
        )
    
    # Poll ElevenLabs API for status
    try:
        status_response = elevenlabs_client.get_composition_status(task_id)
        
        # Extract status from response
        # Adjust based on actual SDK response structure
        new_status = 'processing'
        if hasattr(status_response, 'status'):
            new_status = status_response.status
        elif isinstance(status_response, dict):
            new_status = status_response.get('status', 'processing')
        
        # Update local task status
        task['status'] = new_status
        if hasattr(status_response, 'progress'):
            task['progress'] = status_response.progress
        elif isinstance(status_response, dict) and 'progress' in status_response:
            task['progress'] = status_response['progress']
        
        # Check if completed
        if new_status == 'completed':
            task['status'] = 'completed'
            task['message'] = 'Music generation completed'
        elif new_status == 'failed':
            task['status'] = 'failed'
            task['message'] = getattr(status_response, 'message', 'Music generation failed')
        
        return StatusResponse(
            task_id=task_id,
            status=task['status'],
            progress=task.get('progress'),
            message=task.get('message')
        )
    except NotImplementedError:
        # If status checking is not implemented in SDK, return pending
        return StatusResponse(
            task_id=task_id,
            status='processing',
            message='Status checking not available - assuming processing'
        )
    except Exception as e:
        # On error, return current status
        return StatusResponse(
            task_id=task_id,
            status=current_status,
            message=f"Error checking status: {str(e)}"
        )


@app.get("/api/download/{task_id}")
async def download_music(task_id: str):
    """
    Download generated music file as MP3.
    Returns audio stream when task is completed.
    """
    if not elevenlabs_client:
        raise HTTPException(
            status_code=500,
            detail="ElevenLabs client not initialized"
        )
    
    # Check if task exists
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = tasks[task_id]
    
    # Check if task is completed
    if task.get('status') != 'completed':
        raise HTTPException(
            status_code=400,
            detail=f"Task not completed. Current status: {task.get('status', 'unknown')}"
        )
    
    try:
        # Try to get audio from stored response first
        audio_data = None
        response = task.get('response')
        
        if response:
            # Extract audio from response
            if hasattr(response, 'audio'):
                audio_data = response.audio
            elif isinstance(response, dict) and 'audio' in response:
                audio_data = response['audio']
            elif hasattr(response, 'data'):
                audio_data = response.data
        
        # If not in stored response, fetch from ElevenLabs
        if not audio_data:
            audio_data = elevenlabs_client.get_composition_audio(task_id)
        
        # Convert to bytes if needed
        if isinstance(audio_data, bytes):
            audio_bytes = audio_data
        elif hasattr(audio_data, 'read'):
            audio_bytes = audio_data.read()
        else:
            audio_bytes = bytes(audio_data)
        
        # Return as streaming response
        return StreamingResponse(
            io.BytesIO(audio_bytes),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f"attachment; filename=generated-music-{task_id}.mp3"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve audio: {str(e)}")


@app.get("/api/credits", response_model=CreditsResponse)
async def get_credits():
    """
    Get remaining credits from ElevenLabs subscription.
    """
    if not elevenlabs_client:
        raise HTTPException(
            status_code=500,
            detail="ElevenLabs client not initialized"
        )
    
    try:
        subscription = elevenlabs_client.get_subscription()
        logger.info(f"Subscription response type: {type(subscription)}")
        logger.info(f"Subscription response: {subscription}")
        
        # Handle different response formats more robustly
        subscription_data = {}
        
        if isinstance(subscription, dict):
            subscription_data = subscription
        elif hasattr(subscription, 'model_dump'):
            # Pydantic v2
            subscription_data = subscription.model_dump()
        elif hasattr(subscription, 'dict'):
            # Pydantic v1
            subscription_data = subscription.dict()
        elif hasattr(subscription, '__dict__'):
            subscription_data = subscription.__dict__
        else:
            # Try to access attributes directly
            subscription_data = {
                'remaining_credits': getattr(subscription, 'remaining_credits', None),
                'total_credits': getattr(subscription, 'total_credits', None),
                'character_count': getattr(subscription, 'character_count', None),
                'character_limit': getattr(subscription, 'character_limit', None),
                'tier': getattr(subscription, 'tier', None),
                'subscription_tier': getattr(subscription, 'subscription_tier', None),
            }
        
        logger.info(f"Parsed subscription_data: {subscription_data}")
        
        # Extract credits from nested subscription object
        subscription_obj = subscription_data.get('subscription', {})
        
        # Extract character_count and character_limit from nested subscription
        remaining = subscription_obj.get('character_count')
        total = subscription_obj.get('character_limit')
        tier = subscription_obj.get('tier')
        
        # Fallback to top-level if not found in nested structure
        if remaining is None:
            remaining = subscription_data.get('character_count')
        if total is None:
            total = subscription_data.get('character_limit')
        if tier is None:
            tier = subscription_data.get('tier') or subscription_data.get('subscription_tier')
        
        return CreditsResponse(
            remaining_credits=float(remaining) if remaining is not None else None,
            total_credits=float(total) if total is not None else None,
            subscription_tier=tier
        )
    except ValueError as e:
        # Handle type conversion errors
        logger.error(f"Value conversion error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Invalid response format: {str(e)}")
    except Exception as e:
        logger.error(f"Error fetching credits: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch credits: {str(e)}")


@app.get("/api/credits/debug")
async def debug_credits():
    """Debug endpoint to see raw subscription response"""
    if not elevenlabs_client:
        return {"error": "Client not initialized"}
    
    try:
        subscription = elevenlabs_client.get_subscription()
        return {
            "type": str(type(subscription)),
            "data": subscription if isinstance(subscription, dict) else str(subscription),
            "attributes": dir(subscription) if hasattr(subscription, '__dict__') else None,
            "has_dict": hasattr(subscription, '__dict__'),
            "has_model_dump": hasattr(subscription, 'model_dump'),
            "has_dict_method": hasattr(subscription, 'dict'),
        }
    except Exception as e:
        return {"error": str(e), "type": str(type(e)), "traceback": str(e.__traceback__)}


# Voice Conversion Processing Pipeline
async def process_voice_conversion(
    job_id: str,
    input_file_path: str,
    temp_dir: str,
    f0_up_key: int = 0,
    f0_method: str = "rmvpe",
    index_rate: float = 0.75,
    filter_radius: int = 3,
    rms_mix_rate: float = 0.25,
    protect: float = 0.33,
    resample_sr: int = 0
):
    """
    Background task to process voice conversion using RVC.
    """
    try:
        voice_conversion_jobs[job_id]['status'] = 'processing'
        voice_conversion_jobs[job_id]['message'] = 'Starting voice conversion...'
        
        # Convert input to WAV if needed (RVC works best with WAV)
        input_path = Path(input_file_path)
        input_wav_path = os.path.join(temp_dir, f"input_{job_id}.wav")
        
        # If not WAV, convert using ffmpeg (if available) or use as-is
        if input_path.suffix.lower() != '.wav':
            logger.info(f"Job {job_id}: Converting input to WAV format")
            try:
                import subprocess
                subprocess.run(
                    ['ffmpeg', '-i', input_file_path, '-y', input_wav_path],
                    check=True,
                    capture_output=True
                )
                input_file_path = input_wav_path
            except (subprocess.CalledProcessError, FileNotFoundError):
                logger.warning(f"Job {job_id}: FFmpeg not available, using original file format")
                # RVC might still work with other formats, but WAV is recommended
        
        # Perform voice conversion
        logger.info(f"Job {job_id}: Performing voice conversion")
        output_wav_path = os.path.join(temp_dir, f"output_{job_id}.wav")
        
        rvc_client.convert_voice(
            input_path=input_file_path,
            output_path=output_wav_path,
            sid=0,  # Default speaker ID
            f0_up_key=f0_up_key,
            f0_method=f0_method,
            index_rate=index_rate,
            filter_radius=filter_radius,
            rms_mix_rate=rms_mix_rate,
            protect=protect,
            resample_sr=resample_sr
        )
        
        # Convert output to MP3 for download
        logger.info(f"Job {job_id}: Converting output to MP3")
        output_mp3_path = os.path.join(temp_dir, f"output_{job_id}.mp3")
        try:
            import subprocess
            subprocess.run(
                ['ffmpeg', '-i', output_wav_path, '-y', '-codec:a', 'libmp3lame', '-q:a', '2', output_mp3_path],
                check=True,
                capture_output=True
            )
            final_output_path = output_mp3_path
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning(f"Job {job_id}: FFmpeg not available for MP3 conversion, using WAV")
            final_output_path = output_wav_path
        
        voice_conversion_jobs[job_id]['output_path'] = final_output_path
        voice_conversion_jobs[job_id]['status'] = 'completed'
        voice_conversion_jobs[job_id]['message'] = 'Voice conversion completed!'
        logger.info(f"Job {job_id}: Processing complete")
        
    except Exception as e:
        logger.error(f"Job {job_id}: Processing failed: {str(e)}", exc_info=True)
        voice_conversion_jobs[job_id]['status'] = 'failed'
        voice_conversion_jobs[job_id]['message'] = f'Processing failed: {str(e)}'
        voice_conversion_jobs[job_id]['error'] = str(e)


@app.post("/api/voice-conversion/upload", response_model=VoiceConversionResponse)
async def upload_voice_conversion(
    background_tasks: BackgroundTasks,
    audio_file: UploadFile = File(...),
    f0_up_key: int = Form(0),
    f0_method: str = Form("rmvpe"),
    index_rate: float = Form(0.75),
    filter_radius: int = Form(3),
    rms_mix_rate: float = Form(0.25),
    protect: float = Form(0.33),
    resample_sr: int = Form(0)
):
    """
    Upload an audio file and start voice conversion process.
    """
    if not rvc_client or not rvc_client.is_available():
        raise HTTPException(
            status_code=500,
            detail="RVC client not initialized. Please ensure a model file is placed in assets/weights/"
        )
    
    job_id = str(uuid.uuid4())
    temp_dir = tempfile.mkdtemp(prefix=f"voice_conversion_{job_id}_")
    
    try:
        # Save uploaded file to temp directory
        input_file_path = os.path.join(temp_dir, f"input_{job_id}{Path(audio_file.filename).suffix}")
        async with aiofiles.open(input_file_path, 'wb') as f:
            content = await audio_file.read()
            await f.write(content)
        
        # Initialize job tracking
        voice_conversion_jobs[job_id] = {
            'status': 'pending',
            'created_at': datetime.now(),
            'input_file_path': input_file_path,
            'temp_dir': temp_dir,
            'message': 'Starting processing...'
        }
        
        # Start background processing
        background_tasks.add_task(
            process_voice_conversion,
            job_id,
            input_file_path,
            temp_dir,
            f0_up_key,
            f0_method,
            index_rate,
            filter_radius,
            rms_mix_rate,
            protect,
            resample_sr
        )
        
        return VoiceConversionResponse(
            job_id=job_id,
            status='pending',
            message='Voice conversion started'
        )
    
    except Exception as e:
        logger.error(f"Job {job_id}: Upload failed: {str(e)}", exc_info=True)
        # Clean up temp directory on error
        try:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        except:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to start processing: {str(e)}")


@app.get("/api/voice-conversion/status/{job_id}", response_model=VoiceConversionStatusResponse)
async def get_voice_conversion_status(job_id: str):
    """
    Get status of a voice conversion job.
    """
    if job_id not in voice_conversion_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = voice_conversion_jobs[job_id]
    
    # Calculate progress if processing
    progress = None
    if job['status'] == 'processing':
        # Simple progress estimation
        progress = 50  # Processing is in progress
    
    return VoiceConversionStatusResponse(
        job_id=job_id,
        status=job['status'],
        progress=progress,
        message=job.get('message', '')
    )


@app.get("/api/voice-conversion/download/{job_id}")
async def download_voice_conversion(job_id: str):
    """
    Download the converted audio file.
    """
    if job_id not in voice_conversion_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = voice_conversion_jobs[job_id]
    
    if job['status'] != 'completed':
        raise HTTPException(
            status_code=400,
            detail=f"Job not completed. Current status: {job['status']}"
        )
    
    output_path = job.get('output_path')
    if not output_path or not os.path.exists(output_path):
        raise HTTPException(
            status_code=404,
            detail="Output file not found"
        )
    
    try:
        async with aiofiles.open(output_path, 'rb') as f:
            audio_bytes = await f.read()
        
        # Determine media type based on file extension
        ext = Path(output_path).suffix.lower()
        media_type = "audio/mpeg" if ext == ".mp3" else "audio/wav"
        filename = f"voice-converted-{job_id}{ext}"
        
        return StreamingResponse(
            io.BytesIO(audio_bytes),
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        logger.error(f"Failed to download converted audio: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve audio: {str(e)}")
