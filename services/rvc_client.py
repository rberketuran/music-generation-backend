import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from scipy.io import wavfile
import numpy as np

load_dotenv()

logger = logging.getLogger(__name__)


class RVCClient:
    """
    Client for RVC (Retrieval-based Voice Conversion) library.
    Handles voice conversion using RVC models.
    """
    
    def __init__(self):
        """
        Initialize RVC client with model paths from environment variables.
        """
        # Get model paths from environment or use defaults
        self.model_path = os.getenv(
            "RVC_MODEL_PATH",
            os.path.join("assets", "weights", "default.pth")
        )
        self.index_path = os.getenv(
            "RVC_INDEX_PATH",
            os.path.join("assets", "indices", "default.index")
        )
        
        # Check if model file exists
        if not os.path.exists(self.model_path):
            logger.warning(f"RVC model not found at {self.model_path}")
            logger.warning("Voice conversion features will be disabled. Please place a .pth model file in assets/weights/")
            self.vc = None
            return
        
        try:
            # Import RVC modules
            from rvc.modules.vc.modules import VC
            
            # Initialize VC module
            self.vc = VC()
            
            # Load the model
            logger.info(f"Loading RVC model from {self.model_path}")
            self.vc.get_vc(self.model_path)
            
            # Check if index file exists (optional but recommended)
            if os.path.exists(self.index_path):
                logger.info(f"Using index file: {self.index_path}")
            else:
                logger.info(f"Index file not found at {self.index_path} (optional, continuing without it)")
            
            logger.info("RVC client initialized successfully")
        except ImportError as e:
            logger.error(f"Failed to import RVC library: {e}")
            logger.error("Please install RVC: pip install git+https://github.com/RVC-Project/Retrieval-based-Voice-Conversion")
            self.vc = None
        except Exception as e:
            logger.error(f"Failed to initialize RVC client: {e}")
            self.vc = None
    
    def is_available(self):
        """Check if RVC client is available and ready."""
        return self.vc is not None
    
    def convert_voice(
        self,
        input_path: str,
        output_path: str,
        sid: int = 0,
        f0_up_key: int = 0,
        f0_method: str = "rmvpe",
        index_rate: float = 0.75,
        filter_radius: int = 3,
        rms_mix_rate: float = 0.25,
        protect: float = 0.33,
        resample_sr: int = 0,
        f0_file: str = None,
        index_file: str = None
    ):
        """
        Convert voice using RVC model.
        
        Args:
            input_path: Path to input audio file
            output_path: Path to save output audio file
            sid: Speaker/Singer ID (default: 0)
            f0_up_key: Transpose in semitones (default: 0)
            f0_method: Pitch extraction method - pm, harvest, crepe, rmvpe (default: rmvpe)
            index_rate: Search feature ratio 0-1 (default: 0.75)
            filter_radius: Median filter radius (default: 3)
            rms_mix_rate: Volume envelope scaling 0-1 (default: 0.25)
            protect: Protect voiceless consonants 0-0.5 (default: 0.33)
            resample_sr: Resample output to this sample rate, 0 for no resampling (default: 0)
            f0_file: Optional F0 curve file path
            index_file: Optional index file path (overrides default)
        
        Returns:
            tuple: (sample_rate, audio_data, processing_times)
        """
        if not self.is_available():
            raise RuntimeError("RVC client is not available. Check model configuration.")
        
        try:
            # Use provided index file or default
            index_path = index_file if index_file else (self.index_path if os.path.exists(self.index_path) else None)
            
            # Perform voice conversion
            logger.info(f"Converting voice: {input_path} -> {output_path}")
            tgt_sr, audio_opt, times, _ = self.vc.vc_inference(
                sid=sid,
                input_path=Path(input_path),
                f0_up_key=f0_up_key,
                f0_method=f0_method,
                index_rate=index_rate,
                filter_radius=filter_radius,
                rms_mix_rate=rms_mix_rate,
                protect=protect,
                resample_sr=resample_sr,
                f0_file=Path(f0_file) if f0_file else None,
                index_path=Path(index_path) if index_path else None
            )
            
            # Save output audio
            wavfile.write(output_path, tgt_sr, audio_opt)
            logger.info(f"Voice conversion completed: {output_path}")
            
            return tgt_sr, audio_opt, times
        except Exception as e:
            logger.error(f"Voice conversion failed: {e}", exc_info=True)
            raise Exception(f"Failed to convert voice: {str(e)}")
