import re
import os
import json
import html
import time
import pickle
import base64
import requests
import traceback
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Any
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

class YouTubeTranscriptFetcher:
    def __init__(self):
        """Initialize the YouTube transcript fetcher with OAuth support"""
        self.api_key = os.environ.get("YOUTUBE_API_KEY")
        self.client_id = os.environ.get("GOOGLE_CLIENT_ID")
        self.client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
        self.oauth_token = os.environ.get("YOUTUBE_OAUTH_TOKEN")
        
        # Define OAuth scopes needed - Updated with all required scopes
        self.scopes = [
            "https://www.googleapis.com/auth/youtube.force-ssl",
            "https://www.googleapis.com/auth/youtube",
            "https://www.googleapis.com/auth/youtube.readonly"
        ]
        
        # Create a session for requests
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        })

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
    
    def _get_youtube_video_info(self, video_id: str) -> Dict:
        """
        Get basic video info using YouTube Data API
        
        Args:
            video_id: YouTube video ID
            
        Returns:
            Video metadata
        """
        youtube = self.get_youtube_service()
        if not youtube:
            return {}
            
        try:
            response = youtube.videos().list(
                part="snippet",
                id=video_id
            ).execute()
            
            if not response.get('items'):
                return {}
                
            return response['items'][0]['snippet']
        except Exception as e:
            print(f"Error getting video info: {e}")
            return {}
            
    def _list_caption_tracks(self, video_id: str) -> List[Dict]:
        """
        List available caption tracks for a video
        
        Args:
            video_id: YouTube video ID
            
        Returns:
            List of available caption tracks
        """
        youtube = self.get_youtube_service()
        if not youtube:
            return []
            
        try:
            response = youtube.captions().list(
                part="snippet",
                videoId=video_id
            ).execute()
            
            return response.get('items', [])
        except Exception as e:
            print(f"Error listing caption tracks: {e}")
            return []
    
    def _get_direct_transcript_url(self, video_id: str, language: str = 'en') -> Optional[str]:
        """
        Get the direct transcript URL (alternative method)
        
        Args:
            video_id: YouTube video ID
            language: Language code
            
        Returns:
            Transcript URL or None
        """
        try:
            # First try to get available captions list
            url = f"https://www.youtube.com/api/timedtext?type=list&v={video_id}"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200 and response.text:
                try:
                    root = ET.fromstring(response.text)
                    available_langs = []
                    
                    for track in root.findall('.//track'):
                        lang_code = track.get('lang_code', '')
                        lang_name = track.get('name', '')
                        available_langs.append((lang_code, lang_name))
                        
                    # Find the requested language or fallbacks
                    target_lang = None
                    
                    # First try exact match
                    for lang_code, lang_name in available_langs:
                        if lang_code == language:
                            target_lang = lang_code
                            break
                            
                    # If not found, try English or any available
                    if not target_lang:
                        for lang_code, lang_name in available_langs:
                            if lang_code == 'en':
                                target_lang = lang_code
                                break
                                
                    if not target_lang and available_langs:
                        target_lang = available_langs[0][0]
                        
                    if target_lang:
                        transcript_url = f"https://www.youtube.com/api/timedtext?lang={target_lang}&v={video_id}"
                        return transcript_url
                        
                except ET.ParseError:
                    print("Error parsing caption list")
                    
            # Try common languages directly
            langs_to_try = [language, 'en', 'en-US', 'en-GB']
            for lang in langs_to_try:
                url = f"https://www.youtube.com/api/timedtext?lang={lang}&v={video_id}"
                response = self.session.get(url, timeout=10)
                if response.status_code == 200 and response.text and len(response.text.strip()) > 0:
                    return url
                    
            # Try with auto-generated captions
            for lang in langs_to_try:
                url = f"https://www.youtube.com/api/timedtext?lang={lang}&v={video_id}&kind=asr"
                response = self.session.get(url, timeout=10)
                if response.status_code == 200 and response.text and len(response.text.strip()) > 0:
                    return url
            
            return None
            
        except Exception as e:
            print(f"Error getting direct transcript URL: {e}")
            return None
            
    def _get_transcript_from_url(self, url: str) -> List[Dict[str, Any]]:
        """
        Parse transcript from a direct URL
        
        Args:
            url: Transcript URL
            
        Returns:
            List of transcript segments
        """
        try:
            response = self.session.get(url, timeout=10)
            if response.status_code != 200 or not response.text:
                return []
                
            # Parse XML
            try:
                root = ET.fromstring(response.text)
                segments = []
                
                for text in root.findall('.//text'):
                    start = float(text.get('start', 0))
                    duration = float(text.get('dur', 0))
                    content = text.text or ''
                    
                    # Unescape HTML entities
                    if '&' in content:
                        content = html.unescape(content)
                    
                    segments.append({
                        "text": content.strip(),
                        "start": start,
                        "duration": duration
                    })
                
                if segments:
                    print(f"Successfully retrieved {len(segments)} transcript segments")
                    return segments
                    
            except ET.ParseError as e:
                print(f"Error parsing transcript XML: {e}")
                
            return []
            
        except Exception as e:
            print(f"Error getting transcript from URL: {e}")
            return []
    
    def _get_transcript_from_invidious(self, video_id: str, language: str = 'en') -> List[Dict[str, Any]]:
        """
        Try to get transcript using Invidious instances
        
        Args:
            video_id: YouTube video ID
            language: Language code
            
        Returns:
            List of transcript segments
        """
        instances = [
            "https://invidious.snopyta.org",
            "https://yewtu.be",
            "https://vid.puffyan.us",
            "https://invidious.kavin.rocks"
        ]
        
        for instance in instances:
            try:
                url = f"{instance}/api/v1/captions/{video_id}"
                print(f"Trying Invidious instance: {url}")
                
                response = self.session.get(url, timeout=10)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        captions = data.get("captions", [])
                        
                        if not captions:
                            continue
                            
                        # Find caption in requested language
                        caption_url = None
                        for caption in captions:
                            if caption.get("language_code") == language:
                                caption_url = caption.get("url")
                                break
                                
                        # If not found, try English or any available
                        if not caption_url:
                            for caption in captions:
                                if caption.get("language_code") == "en":
                                    caption_url = caption.get("url")
                                    break
                                    
                        if not caption_url and captions:
                            caption_url = captions[0].get("url")
                            
                        if caption_url:
                            caption_response = self.session.get(caption_url, timeout=10)
                            if caption_response.status_code == 200:
                                try:
                                    captions_data = caption_response.json()
                                    segments = []
                                    
                                    for item in captions_data:
                                        segments.append({
                                            "text": item.get("text", ""),
                                            "start": item.get("start", 0),
                                            "duration": item.get("duration", 0)
                                        })
                                        
                                    if segments:
                                        print(f"Successfully retrieved {len(segments)} transcript segments from Invidious")
                                        return segments
                                except:
                                    print("Error parsing Invidious caption data")
                    except:
                        print(f"Error parsing response from Invidious instance {instance}")
            except Exception as e:
                print(f"Error accessing Invidious instance {instance}: {e}")
                
        return []
    
    def get_transcript(self, video_id: str, language: str = 'en') -> List[Dict[str, Any]]:
        """
        Get transcript for a YouTube video using multiple methods
        
        Args:
            video_id: YouTube video ID
            language: Language code (default: 'en')
            
        Returns:
            List of transcript segments
        """
        print(f"Fetching transcript for video {video_id} in language {language}")
        
        # Method 1: List captions using OAuth to see if they exist
        captions = self._list_caption_tracks(video_id)
        if captions:
            print(f"Found {len(captions)} caption tracks via OAuth")
            
            # Note: We won't try to download via OAuth since it typically fails with permission errors
            # Instead, we'll use alternative methods to get the content
        
        # Method 2: Try to get direct transcript URL
        transcript_url = self._get_direct_transcript_url(video_id, language)
        if transcript_url:
            print(f"Found direct transcript URL: {transcript_url}")
            segments = self._get_transcript_from_url(transcript_url)
            if segments:
                return segments
        
        # Method 3: Try Invidious API (alternative front-end)
        segments = self._get_transcript_from_invidious(video_id, language)
        if segments:
            return segments
        
        # If we've verified captions exist via OAuth but couldn't get them directly,
        # we'll try one more approach: Using HTML scraping as a last resort
        if captions:
            try:
                print("Attempting to get transcript via HTML approach as last resort")
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                response = self.session.get(video_url, timeout=15)
                
                if response.status_code == 200:
                    # Try to find the caption track JSON in the HTML
                    caption_json_pattern = r'"captionTracks":\[(.*?)\]'
                    match = re.search(caption_json_pattern, response.text)
                    
                    if match:
                        caption_data = "[" + match.group(1) + "]"
                        caption_data = caption_data.replace('\\u0026', '&')
                        
                        try:
                            tracks = json.loads(caption_data)
                            if tracks:
                                # Find base URL for the transcript
                                base_url = None
                                for track in tracks:
                                    track_lang = track.get("languageCode")
                                    if track_lang == language or track_lang == "en" or base_url is None:
                                        base_url = track.get("baseUrl")
                                        if track_lang == language:
                                            break
                                
                                if base_url:
                                    # Format might be different, try both
                                    urls_to_try = [
                                        f"{base_url}&fmt=json3",
                                        base_url
                                    ]
                                    
                                    for url in urls_to_try:
                                        try:
                                            data_response = self.session.get(url, timeout=10)
                                            if data_response.status_code == 200:
                                                # Try to parse as JSON first
                                                try:
                                                    json_data = data_response.json()
                                                    segments = []
                                                    
                                                    # Parse JSON format
                                                    if "events" in json_data:
                                                        for event in json_data["events"]:
                                                            if "segs" in event:
                                                                start = event.get("tStartMs", 0) / 1000
                                                                duration = event.get("dDurationMs", 0) / 1000
                                                                
                                                                text_parts = []
                                                                for seg in event["segs"]:
                                                                    if "utf8" in seg:
                                                                        text_parts.append(seg["utf8"])
                                                                
                                                                if text_parts:
                                                                    segments.append({
                                                                        "text": "".join(text_parts).strip(),
                                                                        "start": start,
                                                                        "duration": duration
                                                                    })
                                                    
                                                    if segments:
                                                        print(f"Successfully retrieved {len(segments)} transcript segments via HTML approach")
                                                        return segments
                                                        
                                                except json.JSONDecodeError:
                                                    # Try to parse as XML
                                                    try:
                                                        return self._get_transcript_from_url(url)
                                                    except:
                                                        pass
                                        except:
                                            continue
                        except:
                            print("Error parsing caption data from HTML")
            except Exception as e:
                print(f"Error with HTML approach: {e}")
        
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
        
    def diagnose_transcript_access(self, video_id):
        """
        Diagnose issues with transcript access using YouTube Data API
        
        Args:
            video_id: YouTube video ID
            
        Returns:
            Dict with diagnostic information
        """
        diagnostics = {
            "video_id": video_id,
            "timestamp": datetime.now().isoformat(),
            "api_key_present": bool(self.api_key),
            "oauth_token_present": bool(self.oauth_token),
            "steps": [],
            "transcript_found": False,
            "error": None
        }
        
        try:
            # Step 1: Check if we can get video info
            diagnostics["steps"].append({"step": "Get video info", "status": "attempting"})
            video_info = self._get_youtube_video_info(video_id)
            
            if video_info:
                diagnostics["steps"][-1]["status"] = "success"
                diagnostics["video_title"] = video_info.get("title")
                diagnostics["video_channel"] = video_info.get("channelTitle")
                diagnostics["has_captions"] = video_info.get("caption", False)
            else:
                diagnostics["steps"][-1]["status"] = "failed"
                diagnostics["steps"][-1]["error"] = "Could not retrieve video info"
                return diagnostics
            
            # Step 2: Check if caption tracks exist using the Data API
            diagnostics["steps"].append({"step": "List caption tracks", "status": "attempting"})
            youtube = self.get_youtube_service()
            
            if not youtube:
                diagnostics["steps"][-1]["status"] = "failed"
                diagnostics["steps"][-1]["error"] = "Could not create YouTube service (OAuth issues)"
                return diagnostics
            
            try:
                captions_response = youtube.captions().list(
                    part="snippet",
                    videoId=video_id
                ).execute()
                
                captions = captions_response.get("items", [])
                diagnostics["steps"][-1]["status"] = "success"
                diagnostics["caption_tracks_count"] = len(captions)
                
                if captions:
                    diagnostics["caption_tracks"] = []
                    for caption in captions:
                        track_info = {
                            "id": caption.get("id"),
                            "language": caption.get("snippet", {}).get("language"),
                            "language_name": caption.get("snippet", {}).get("name"),
                            "track_kind": caption.get("snippet", {}).get("trackKind"),
                            "is_cc": caption.get("snippet", {}).get("trackKind") == "closedCaption",
                            "is_asr": caption.get("snippet", {}).get("trackKind") == "ASR"
                        }
                        diagnostics["caption_tracks"].append(track_info)
                else:
                    diagnostics["steps"][-1]["note"] = "No caption tracks found"
                    return diagnostics
                
                # Step 3: Try to download a caption track
                diagnostics["steps"].append({"step": "Download caption track", "status": "attempting"})
                
                # Find an English track or use the first available
                caption_id = None
                for track in diagnostics["caption_tracks"]:
                    if track["language"] == "en":
                        caption_id = track["id"]
                        break
                
                if not caption_id and diagnostics["caption_tracks"]:
                    caption_id = diagnostics["caption_tracks"][0]["id"]
                
                if caption_id:
                    try:
                        # Try to download the caption track
                        caption_response = youtube.captions().download(
                            id=caption_id,
                            tfmt="srt"
                        ).execute()
                        
                        # If we get here, it succeeded
                        diagnostics["steps"][-1]["status"] = "success"
                        diagnostics["transcript_found"] = True
                        
                        # Include a sample of the transcript if available
                        if isinstance(caption_response, bytes):
                            sample = caption_response[:200].decode('utf-8', errors='replace')
                            diagnostics["transcript_sample"] = sample
                        
                    except HttpError as e:
                        diagnostics["steps"][-1]["status"] = "failed"
                        diagnostics["steps"][-1]["error"] = str(e)
                        
                        # Extract specific error reason
                        error_reason = "Unknown error"
                        if hasattr(e, 'reason'):
                            error_reason = e.reason
                        elif hasattr(e, 'content'):
                            try:
                                error_content = json.loads(e.content.decode('utf-8'))
                                error_reason = error_content.get('error', {}).get('message', 'Unknown error')
                            except:
                                pass
                        
                        diagnostics["error"] = error_reason
                else:
                    diagnostics["steps"][-1]["status"] = "failed"
                    diagnostics["steps"][-1]["error"] = "No caption ID found to download"
            
            except HttpError as e:
                diagnostics["steps"][-1]["status"] = "failed"
                diagnostics["steps"][-1]["error"] = str(e)
                diagnostics["error"] = str(e)
            
            # Step 4: Try alternative methods if OAuth method failed
            if not diagnostics["transcript_found"]:
                diagnostics["steps"].append({"step": "Try alternative methods", "status": "attempting"})
                
                # Try direct URL method
                transcript_url = self._get_direct_transcript_url(video_id, "en")
                if transcript_url:
                    diagnostics["steps"][-1]["status"] = "success"
                    diagnostics["steps"][-1]["method"] = "direct_url"
                    diagnostics["transcript_found"] = True
                    diagnostics["transcript_url"] = transcript_url
                else:
                    # Try Invidious as a last resort
                    segments = self._get_transcript_from_invidious(video_id, "en")
                    if segments:
                        diagnostics["steps"][-1]["status"] = "success"
                        diagnostics["steps"][-1]["method"] = "invidious"
                        diagnostics["transcript_found"] = True
                        diagnostics["segments_count"] = len(segments)
                    else:
                        diagnostics["steps"][-1]["status"] = "failed"
                        diagnostics["steps"][-1]["error"] = "All methods failed to find transcript"
        
        except Exception as e:
            # Catch any unexpected errors
            diagnostics["error"] = str(e)
            diagnostics["traceback"] = traceback.format_exc()
        
        return diagnostics