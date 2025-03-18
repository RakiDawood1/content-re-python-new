import os
import requests
from dotenv import load_dotenv
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
import io
import re
from typing import List, Dict, Optional, Any

class YouTubeDataAPITranscriptFetcher:
    def __init__(self):
        """Initialize the YouTube Data API transcript fetcher"""
        # Load environment variables
        load_dotenv()
        
        # Get API key
        self.api_key = os.environ.get("YOUTUBE_API_KEY")
        if not self.api_key:
            print("Warning: YOUTUBE_API_KEY environment variable not found")
            
        # Initialize YouTube API client
        self.youtube = build('youtube', 'v3', developerKey=self.api_key)
        
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
        
    def get_caption_tracks(self, video_id: str) -> List[Dict[str, Any]]:
        """
        Get a list of all available caption tracks for a YouTube video
        
        Args:
            video_id: YouTube video ID
            
        Returns:
            List of caption track information
        """
        try:
            # Call the captions.list method to retrieve caption tracks
            results = self.youtube.captions().list(
                part="snippet",
                videoId=video_id
            ).execute()
            
            return results.get("items", [])
        except Exception as e:
            print(f"Error fetching caption tracks: {e}")
            return []
    
    def download_caption(self, caption_id: str, format: str = 'srt', language: str = None) -> str:
        """
        Download a specific caption track
        
        Args:
            caption_id: The ID of the caption track
            format: The format to download the caption in (e.g., 'srt', 'vtt')
            language: Optional language to translate the captions to
            
        Returns:
            Caption content as string
        """
        try:
            # Prepare request parameters
            params = {
                'id': caption_id,
                'tfmt': format
            }
            
            # Add language parameter if specified
            if language:
                params['tlang'] = language
                
            # Use the captions.download method
            request = self.youtube.captions().download(**params)
            
            # Execute the request
            response = request.execute()
            
            # Return the caption content
            return response.decode('utf-8')
        except Exception as e:
            print(f"Error downloading caption: {e}")
            return ""
            
    def get_transcript(self, video_id: str, language: str = 'en') -> List[Dict[str, Any]]:
        """
        Get transcript for a YouTube video using YouTube Data API
        
        Args:
            video_id: YouTube video ID
            language: Language code (default: 'en')
            
        Returns:
            List of transcript segments
            
        Raises:
            Exception: If transcript cannot be retrieved
        """
        print(f"Fetching transcript for video {video_id} in language {language}")
        
        try:
            # Get all caption tracks for the video
            caption_tracks = self.get_caption_tracks(video_id)
            
            if not caption_tracks:
                raise Exception(f"No caption tracks found for video {video_id}")
            
            # Filter tracks to find the requested language
            target_track = None
            for track in caption_tracks:
                track_language = track['snippet']['language']
                is_auto_generated = track['snippet'].get('trackKind') == 'ASR'
                
                # First check for exact language match
                if track_language == language:
                    # Prefer manual captions over auto-generated
                    if not is_auto_generated or target_track is None:
                        target_track = track
                        if not is_auto_generated:
                            break
            
            # If no exact language match, look for any caption track
            if target_track is None and caption_tracks:
                target_track = caption_tracks[0]
                print(f"No captions in {language} found. Using {target_track['snippet']['language']} instead.")
            
            if target_track:
                # Download the caption track
                caption_id = target_track['id']
                caption_content = self.download_caption(caption_id, format='srt')
                
                # Parse SRT formatted content into segments
                segments = self.parse_srt(caption_content)
                return segments
            else:
                raise Exception(f"Could not find suitable caption track for video {video_id}")
            
        except Exception as e:
            print(f"Error fetching transcript: {e}")
            
            # Return a fallback message as a single segment
            return [{
                "text": f"I'm sorry, the transcript for this video ({video_id}) is unavailable. The video likely doesn't have captions enabled or they're not accessible. Please try a different video with captions enabled.",
                "start": 0,
                "duration": 10,
                "isUnavailableMessage": True
            }]
    
    def parse_srt(self, srt_content: str) -> List[Dict[str, Any]]:
        """
        Parse SRT formatted captions into segments
        
        Args:
            srt_content: SRT formatted caption content
            
        Returns:
            List of transcript segments
        """
        segments = []
        
        # SRT format pattern: sequence number, time range, text, blank line
        pattern = r'(\d+)\s*\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\n([\s\S]*?)(?=\n\s*\n|\Z)'
        
        matches = re.findall(pattern, srt_content)
        
        for match in matches:
            sequence, start_time, end_time, text = match
            
            # Convert time format HH:MM:SS,mmm to seconds
            start_seconds = self._time_to_seconds(start_time)
            end_seconds = self._time_to_seconds(end_time)
            duration = end_seconds - start_seconds
            
            segments.append({
                "text": text.strip().replace('\n', ' '),
                "start": start_seconds,
                "duration": duration
            })
        
        return segments
    
    def _time_to_seconds(self, time_str: str) -> float:
        """
        Convert SRT time format (HH:MM:SS,mmm) to seconds
        
        Args:
            time_str: Time string in HH:MM:SS,mmm format
            
        Returns:
            Time in seconds as float
        """
        hours, minutes, seconds = time_str.replace(',', '.').split(':')
        return float(hours) * 3600 + float(minutes) * 60 + float(seconds)