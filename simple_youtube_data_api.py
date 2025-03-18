import os
import json
import base64
import pickle
from typing import Dict, List, Optional, Any
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

class SimpleYouTubeAPI:
    def __init__(self):
        """Initialize with just YouTube Data API and OAuth"""
        self.api_key = os.environ.get("YOUTUBE_API_KEY")
        self.oauth_token = os.environ.get("YOUTUBE_OAUTH_TOKEN")
        self.client_id = os.environ.get("GOOGLE_CLIENT_ID")
        self.client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
        
        # Define OAuth scopes
        self.scopes = [
            "https://www.googleapis.com/auth/youtube.force-ssl",
            "https://www.googleapis.com/auth/youtube",
            "https://www.googleapis.com/auth/youtube.readonly"
        ]
        
        print(f"Initialized with API key: {bool(self.api_key)}, OAuth token: {bool(self.oauth_token)}")
    
    def get_credentials_from_token(self, token_data: str) -> Optional[Credentials]:
        """Reconstruct credentials from stored token data"""
        try:
            token_bytes = base64.b64decode(token_data)
            token_dict = pickle.loads(token_bytes)
            
            # Print token details for debugging
            print(f"Token scopes: {token_dict.get('scopes')}")
            print(f"Has refresh token: {bool(token_dict.get('refresh_token'))}")
            
            return Credentials(
                token=token_dict.get('token'),
                refresh_token=token_dict.get('refresh_token'),
                token_uri=token_dict.get('token_uri', "https://oauth2.googleapis.com/token"),
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=token_dict.get('scopes', self.scopes)
            )
        except Exception as e:
            print(f"Error reconstructing credentials: {e}")
            return None
    
    def get_youtube_service(self) -> Optional[Any]:
        """Get an authenticated YouTube service client"""
        if not self.oauth_token:
            print("No OAuth token available. Authentication required.")
            return None
            
        try:
            # Get credentials from stored token
            credentials = self.get_credentials_from_token(self.oauth_token)
            
            if not credentials:
                print("Invalid OAuth token. Re-authentication required.")
                return None
                
            # Build the YouTube service
            youtube = build('youtube', 'v3', credentials=credentials)
            print("Successfully built YouTube service")
            return youtube
            
        except Exception as e:
            print(f"Error creating YouTube service: {e}")
            return None
    
    def debug_oauth_token(self):
        """Debug the OAuth token to see what's in it"""
        if not self.oauth_token:
            return {"error": "No OAuth token available"}
        
        try:
            token_bytes = base64.b64decode(self.oauth_token)
            token_dict = pickle.loads(token_bytes)
            
            # Clean the dictionary for display
            safe_dict = {
                "has_token": bool(token_dict.get('token')),
                "has_refresh_token": bool(token_dict.get('refresh_token')),
                "token_uri": token_dict.get('token_uri'),
                "scopes": token_dict.get('scopes', []),
                "expiry": token_dict.get('expiry'),
                "client_id_partial": token_dict.get('client_id', "")[:10] + "..." if token_dict.get('client_id') else None
            }
            
            return safe_dict
        except Exception as e:
            return {"error": f"Error decoding token: {e}"}
    
    def list_captions(self, video_id: str) -> Dict:
        """List all available captions for a video"""
        youtube = self.get_youtube_service()
        
        if not youtube:
            return {"error": "YouTube service not available, check OAuth token"}
        
        try:
            # Call the captions.list method
            request = youtube.captions().list(
                part="snippet",
                videoId=video_id
            )
            response = request.execute()
            
            print(f"Caption list response: {json.dumps(response, indent=2)}")
            
            return response
        except HttpError as e:
            print(f"An HTTP error {e.resp.status} occurred: {e.content}")
            return {"error": f"HTTP error {e.resp.status}", "message": e.content.decode('utf-8')}
        except Exception as e:
            print(f"An error occurred: {e}")
            return {"error": str(e)}
    
    def download_caption(self, caption_id: str) -> Dict:
        """Try to download a specific caption track"""
        youtube = self.get_youtube_service()
        
        if not youtube:
            return {"error": "YouTube service not available, check OAuth token"}
        
        try:
            # Call the captions.download method
            request = youtube.captions().download(
                id=caption_id,
                tfmt="srt"  # Try different formats: srt, vtt, etc.
            )
            
            print("Executing caption download request...")
            response = request.execute()
            
            # If successful, return a sample of the caption
            if isinstance(response, bytes):
                sample = response[:200].decode('utf-8', errors='replace')
                return {
                    "success": True,
                    "sample": sample,
                    "length": len(response)
                }
            
            return {"success": True, "response": response}
        except HttpError as e:
            error_content = e.content.decode('utf-8')
            print(f"An HTTP error {e.resp.status} occurred: {error_content}")
            
            # Parse the error response
            try:
                error_json = json.loads(error_content)
                error_reason = error_json.get("error", {}).get("errors", [{}])[0].get("reason", "unknown")
                error_message = error_json.get("error", {}).get("message", "No message")
                
                return {
                    "error": f"HTTP error {e.resp.status}",
                    "reason": error_reason,
                    "message": error_message,
                    "content": error_content
                }
            except:
                return {
                    "error": f"HTTP error {e.resp.status}",
                    "content": error_content
                }
        except Exception as e:
            print(f"An error occurred: {e}")
            return {"error": str(e)}
    
    def test_video_caption_access(self, video_id: str) -> Dict:
        """Test full caption access for a video"""
        result = {
            "video_id": video_id,
            "api_key_present": bool(self.api_key),
            "oauth_token_present": bool(self.oauth_token),
            "oauth_token_info": self.debug_oauth_token()
        }
        
        # Step 1: List captions
        print(f"Listing captions for video {video_id}...")
        captions_response = self.list_captions(video_id)
        
        if "error" in captions_response:
            result["error"] = captions_response["error"]
            result["captions_error"] = captions_response
            return result
        
        captions = captions_response.get("items", [])
        result["captions_count"] = len(captions)
        
        if not captions:
            result["message"] = "No captions available for this video"
            return result
        
        # Track all available captions
        result["available_captions"] = []
        for caption in captions:
            caption_info = {
                "id": caption.get("id"),
                "language": caption.get("snippet", {}).get("language"),
                "track_kind": caption.get("snippet", {}).get("trackKind")
            }
            result["available_captions"].append(caption_info)
        
        # Step 2: Try to download each caption
        result["download_attempts"] = []
        
        for caption in captions:
            caption_id = caption.get("id")
            language = caption.get("snippet", {}).get("language")
            
            print(f"Attempting to download caption {caption_id} ({language})...")
            download_response = self.download_caption(caption_id)
            
            attempt_info = {
                "caption_id": caption_id,
                "language": language,
                "success": "success" in download_response,
                "response": download_response
            }
            
            result["download_attempts"].append(attempt_info)
            
            # If any download succeeds, we can stop
            if "success" in download_response:
                result["overall_success"] = True
                print(f"Successfully downloaded caption for {language}")
                break
        
        # Overall result
        if not result.get("overall_success"):
            result["overall_success"] = False
            result["message"] = "Failed to download any captions"
        
        return result