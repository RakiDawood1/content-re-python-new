import re
import os
import json
import html
import time
import pickle
import base64
from typing import List, Dict, Optional, Any
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

class YouTubeTranscriptFetcher:
    def __init__(self):
        """Initialize the YouTube transcript fetcher with OAuth support"""
        self.api_key = os.environ.get("YOUTUBE_API_KEY")
        self.client_id = os.environ.get("GOOGLE_CLIENT_ID")
        self.client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
        self.oauth_token = os.environ.get("YOUTUBE_OAUTH_TOKEN")
        
        # Define OAuth scopes needed
        self.scopes = [
            "https://www.googleapis.com/auth/youtube",
            "https://www.googleapis.com/auth/youtube.force-ssl"
        ]

    def extract_video_id(self, url: str) -> Optional[str]:
        """
        Extract YouTube video ID from various URL formats
        
        Args:
            url: YouTube video URL
            
        Returns:
            Video ID or None if not found
        """
        if not url:
            return None
        
        # Standard YouTube URL format
        standard_pattern = r'^.*((youtu.be\/)|(v\/)|(\/u\/\w\/)|(embed\/)|(watch\?))\??v?=?([^#&?]*)'
        match = re.search(standard_pattern, url)
        if match and match.group(7) and len(match.group(7)) == 11:
            return match.group(7)
        
        # YouTube Shorts format
        shorts_pattern = r'^.*((youtube.com\/shorts\/)([^#&?]*))'
        match = re.search(shorts_pattern, url)
        if match and match.group(3):
            return match.group(3)
        
        return None
    
    def create_oauth_flow(self, redirect_uri: str) -> Flow:
        """
        Create an OAuth 2.0 flow for authentication
        
        Args:
            redirect_uri: Redirect URI for OAuth flow
            
        Returns:
            OAuth 2.0 flow
        """
        # Check if we have client credentials
        if not self.client_id or not self.client_secret:
            raise ValueError("Google client ID and client secret are required for OAuth")
        
        # Create a flow instance using client secrets
        client_config = {
            "web": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri]
            }
        }
        
        return Flow.from_client_config(
            client_config,
            scopes=self.scopes,
            redirect_uri=redirect_uri
        )
    
    def get_credentials_from_token(self, token_data: str) -> Credentials:
        """
        Reconstruct credentials from stored token data
        
        Args:
            token_data: Base64 encoded token data
            
        Returns:
            Google API credentials
        """
        # Decode the base64 token
        try:
            token_bytes = base64.b64decode(token_data)
            token_dict = pickle.loads(token_bytes)
            
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
        """
        Get an authenticated YouTube service client
        
        Returns:
            Authenticated YouTube service or None if authentication fails
        """
        # Check if we have a token
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
            return youtube
            
        except Exception as e:
            print(f"Error creating YouTube service: {e}")
            return None
    
    def get_transcript_with_oauth(self, video_id: str, language: str = 'en') -> List[Dict[str, Any]]:
        """
        Get transcript using YouTube Data API with OAuth
        
        Args:
            video_id: YouTube video ID
            language: Language code (default: 'en')
            
        Returns:
            List of transcript segments or empty list if unsuccessful
        """
        youtube = self.get_youtube_service()
        
        if not youtube:
            print("YouTube service is not available. OAuth authentication required.")
            return []
            
        try:
            # List captions for the video
            captions_response = youtube.captions().list(
                part="snippet",
                videoId=video_id
            ).execute()
            
            # Find the caption in the requested language
            caption_id = None
            for item in captions_response.get('items', []):
                caption_language = item['snippet']['language']
                if caption_language == language:
                    caption_id = item['id']
                    print(f"Found caption in requested language: {language}")
                    break
            
            # If not found, try English or any available caption
            if not caption_id:
                for item in captions_response.get('items', []):
                    caption_language = item['snippet']['language']
                    if caption_language == 'en':
                        caption_id = item['id']
                        print("Using English caption as fallback")
                        break
                        
            # If still not found, use the first available caption
            if not caption_id and captions_response.get('items'):
                caption_id = captions_response['items'][0]['id']
                print("Using first available caption")
            
            if not caption_id:
                print("No captions found for this video")
                return []
                
            # Download the caption track
            caption_response = youtube.captions().download(
                id=caption_id,
                tfmt='srt'
            ).execute()
            
            # Parse the SRT format
            segments = []
            srt_lines = caption_response.decode('utf-8').strip().split('\n\n')
            
            for srt_segment in srt_lines:
                lines = srt_segment.split('\n')
                if len(lines) >= 3:
                    # Extract time codes
                    time_line = lines[1]
                    time_parts = time_line.split(' --> ')
                    if len(time_parts) == 2:
                        start_time = self._srt_time_to_seconds(time_parts[0])
                        end_time = self._srt_time_to_seconds(time_parts[1])
                        duration = end_time - start_time
                        
                        # Extract text (could be multiple lines)
                        text = ' '.join(lines[2:])
                        
                        segments.append({
                            "text": text,
                            "start": start_time,
                            "duration": duration
                        })
            
            if segments:
                print(f"Successfully retrieved {len(segments)} transcript segments via OAuth")
                return segments
                
            return []
            
        except Exception as e:
            print(f"Error retrieving transcript with OAuth: {e}")
            return []
    
    def _srt_time_to_seconds(self, time_str: str) -> float:
        """
        Convert SRT time format (00:00:00,000) to seconds
        
        Args:
            time_str: Time string in SRT format
            
        Returns:
            Time in seconds
        """
        hours, minutes, seconds = time_str.replace(',', '.').split(':')
        return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
    
    def get_transcript(self, video_id: str, language: str = 'en') -> List[Dict[str, Any]]:
        """
        Get transcript for a YouTube video
        
        Args:
            video_id: YouTube video ID
            language: Language code (default: 'en')
            
        Returns:
            List of transcript segments
        """
        print(f"Fetching transcript for video {video_id} in language {language}")
        
        # Try OAuth approach first if token is available
        if self.oauth_token:
            segments = self.get_transcript_with_oauth(video_id, language)
            if segments:
                return segments
        
        # Return a fallback message as a single segment
        return [{
            "text": f"I'm sorry, the transcript for this video ({video_id}) is unavailable. The video likely doesn't have captions enabled or they're not accessible. Please try a different video with captions enabled.",
            "start": 0,
            "duration": 10,
            "isUnavailableMessage": True
        }]
    
    def store_credentials(self, credentials: Credentials) -> str:
        """
        Serialize credentials for storage
        
        Args:
            credentials: Google OAuth credentials
            
        Returns:
            Base64 encoded token data
        """
        # Create a dict with the essential credentials data
        token_dict = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes,
            'expiry': credentials.expiry.isoformat() if credentials.expiry else None
        }
        
        # Serialize and encode
        token_bytes = pickle.dumps(token_dict)
        token_b64 = base64.b64encode(token_bytes).decode('utf-8')
        
        return token_b64