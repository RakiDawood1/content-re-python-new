# youtube_html_fetcher.py
import re
import json
import requests
from typing import List, Dict, Optional, Any

class YouTubeHTMLTranscriptFetcher:
    def __init__(self):
        """Initialize the HTML-based YouTube transcript fetcher"""
        # Create a session with common headers
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        })
        
    def extract_video_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from various URL formats"""
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
        
    def get_transcript(self, video_id: str, language: str = 'en') -> List[Dict[str, Any]]:
        """
        Get transcript by extracting directly from YouTube page HTML
        
        Args:
            video_id: YouTube video ID
            language: Language code (default: 'en')
            
        Returns:
            List of transcript segments
        """
        print(f"Fetching transcript via HTML extraction for video {video_id} in language {language}")
        
        try:
            url = f"https://www.youtube.com/watch?v={video_id}"
            response = self.session.get(url, timeout=30)
            
            if response.status_code != 200:
                print(f"Failed to fetch YouTube page: HTTP {response.status_code}")
                return self._create_error_response(video_id)
            
            html_content = response.text
            print(f"Got HTML content, length: {len(html_content)}")
            
            # Find player response data
            player_response_pattern = r'ytInitialPlayerResponse\s*=\s*({.+?});'
            match = re.search(player_response_pattern, html_content)
            
            if not match:
                print("Failed to find player response data in HTML")
                return self._create_error_response(video_id)
            
            try:
                player_response = json.loads(match.group(1))
                caption_tracks = player_response.get('captions', {}).get('playerCaptionsTracklistRenderer', {}).get('captionTracks', [])
                
                if not caption_tracks:
                    print("No caption tracks found in player response data")
                    return self._create_error_response(video_id)
                
                # Log available languages for debugging
                available_langs = [f"{track.get('languageCode')} ({track.get('name', {}).get('simpleText', 'Unknown')})" 
                                  for track in caption_tracks]
                print(f"Available caption tracks: {', '.join(available_langs)}")
                
                # Find target language or fallback to any available
                base_url = None
                selected_lang = None
                
                # First, try exact match for requested language
                for track in caption_tracks:
                    track_lang = track.get('languageCode')
                    if track_lang == language:
                        base_url = track.get('baseUrl')
                        selected_lang = track_lang
                        break
                
                # If not found, try English
                if not base_url:
                    for track in caption_tracks:
                        track_lang = track.get('languageCode')
                        if track_lang == 'en':
                            base_url = track.get('baseUrl')
                            selected_lang = track_lang
                            break
                
                # If still not found, use first available
                if not base_url and caption_tracks:
                    base_url = caption_tracks[0].get('baseUrl')
                    selected_lang = caption_tracks[0].get('languageCode')
                
                if not base_url:
                    print("Failed to find a usable caption track URL")
                    return self._create_error_response(video_id)
                
                print(f"Selected caption track: {selected_lang}")
                print(f"Caption base URL: {base_url}")
                
                # Get caption JSON
                caption_url = f"{base_url}&fmt=json3"
                caption_response = self.session.get(caption_url, timeout=30)
                
                if caption_response.status_code != 200:
                    print(f"Failed to fetch caption JSON: HTTP {caption_response.status_code}")
                    return self._create_error_response(video_id)
                
                try:
                    caption_data = caption_response.json()
                    events = caption_data.get('events', [])
                    
                    segments = []
                    for event in events:
                        if 'segs' not in event:
                            continue
                        
                        start = event.get('tStartMs', 0) / 1000
                        duration = event.get('dDurationMs', 0) / 1000
                        
                        text_parts = []
                        for seg in event.get('segs', []):
                            if 'utf8' in seg:
                                text_parts.append(seg['utf8'])
                        
                        if text_parts:
                            segments.append({
                                "text": ''.join(text_parts).strip(),
                                "start": start,
                                "duration": duration
                            })
                    
                    if segments:
                        print(f"Successfully extracted {len(segments)} transcript segments via HTML method")
                        # Print a few examples for debugging
                        for i, segment in enumerate(segments[:3]):
                            print(f"  {i+1}. [{segment['start']:.2f}s]: {segment['text']}")
                        return segments
                    else:
                        print("No segments found in caption data")
                        return self._create_error_response(video_id)
                        
                except Exception as e:
                    print(f"Error parsing caption JSON: {e}")
                    return self._create_error_response(video_id)
                    
            except Exception as e:
                print(f"Error parsing player response: {e}")
                return self._create_error_response(video_id)
                
        except Exception as e:
            print(f"Error in HTML extraction method: {e}")
            return self._create_error_response(video_id)
            
    def _create_error_response(self, video_id: str) -> List[Dict[str, Any]]:
        """Create a standard error response"""
        return [{
            "text": f"I'm sorry, the transcript for this video ({video_id}) is unavailable. The video likely doesn't have captions enabled or they're not accessible. Please try a different video with captions enabled.",
            "start": 0,
            "duration": 10,
            "isUnavailableMessage": True
        }]