from elevenlabs.client import ElevenLabs
import os
from dotenv import load_dotenv

load_dotenv()


class ElevenLabsClient:
    def __init__(self):
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY not found in environment variables")
        self.api_key = api_key
        self.client = ElevenLabs(api_key=api_key)
    
    def compose_detailed(self, composition_plan):
        """
        Submit composition request to ElevenLabs API.
        Returns response object which should contain task_id.
        """
        try:
            track_details = self.client.music.compose_detailed(
                composition_plan=composition_plan
            )
            return track_details
        except Exception as e:
            raise Exception(f"Failed to submit composition to ElevenLabs: {str(e)}")
    
    def get_composition_status(self, task_id):
        """
        Check status of composition task.
        Note: Exact method name may vary based on SDK version.
        """
        try:
            # The method name may be different - adjust based on actual SDK
            # Possible names: get_status, get_composition_status, check_status
            if hasattr(self.client.music, 'get_status'):
                return self.client.music.get_status(task_id)
            elif hasattr(self.client.music, 'get_composition_status'):
                return self.client.music.get_composition_status(task_id)
            else:
                # Fallback: try to access via HTTP client if needed
                # This is a placeholder - actual implementation depends on SDK
                raise NotImplementedError("Status checking method not found in SDK")
        except Exception as e:
            raise Exception(f"Failed to check composition status: {str(e)}")
    
    def get_composition_audio(self, task_id):
        """
        Retrieve audio when task is complete.
        Returns audio bytes/data.
        """
        try:
            # The method name may be different - adjust based on actual SDK
            if hasattr(self.client.music, 'get_audio'):
                return self.client.music.get_audio(task_id)
            elif hasattr(self.client.music, 'get_composition_audio'):
                return self.client.music.get_composition_audio(task_id)
            else:
                raise NotImplementedError("Audio retrieval method not found in SDK")
        except Exception as e:
            raise Exception(f"Failed to retrieve audio: {str(e)}")
    
    def get_subscription(self):
        """
        Get user subscription information including remaining credits.
        Returns subscription data from ElevenLabs API.
        """
        try:
            # Try SDK methods first
            if hasattr(self.client, 'user'):
                if hasattr(self.client.user, 'get_subscription'):
                    return self.client.user.get_subscription()
                elif hasattr(self.client.user, 'get'):
                    return self.client.user.get()
            
            # Fallback: use direct HTTP request
            import requests
            response = requests.get(
                'https://api.elevenlabs.io/v1/user/subscription',
                headers={'xi-api-key': self.api_key}
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"HTTP request failed: {str(e)}")
        except AttributeError as e:
            raise Exception(f"SDK method not found: {str(e)}")
        except Exception as e:
            raise Exception(f"Failed to fetch subscription: {str(e)}")
