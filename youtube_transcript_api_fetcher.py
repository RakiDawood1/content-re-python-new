import re
from typing import List, Dict, Optional, Any
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

class YouTubeTranscriptFetcher:
    def __init__(self):
        """Initialize the YouTube transcript fetcher"""
        pass
    
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
    
    def get_transcript(self, video_id: str, language: str = 'en') -> List[Dict[str, Any]]:
        """
        Get transcript for a YouTube video using the youtube_transcript_api
        
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
            # First try with the requested language
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # Try to find the requested language
            try:
                transcript = transcript_list.find_transcript([language])
            except:
                # If specific language not found, try to get any available transcript
                print(f"Language {language} not found, trying to get any available transcript")
                transcript = transcript_list.find_transcript(['en'])  # Try English as fallback
                
                # If English also not available, get the first available transcript
                if not transcript:
                    print("English transcript not found, getting the first available transcript")
                    transcript = next(transcript_list._manually_created_transcripts.values().__iter__(), None)
                    
                    # If still no transcript, try auto-generated
                    if not transcript:
                        transcript = next(transcript_list._generated_transcripts.values().__iter__(), None)
            
            # If we found a transcript, get it
            if transcript:
                # Get the transcript data
                data = transcript.fetch()
                
                # Convert to our expected format
                segments = []
                for item in data:
                    segments.append({
                        "text": item['text'],
                        "start": item['start'],
                        "duration": item['duration']
                    })
                
                print(f"Successfully retrieved {len(segments)} transcript segments")
                return segments
            else:
                raise Exception("No transcript available for this video")
                
        except Exception as e:
            print(f"Error fetching transcript: {e}")
            
            # Return a fallback message as a single segment
            return [{
                "text": f"I'm sorry, the transcript for this video ({video_id}) is unavailable. The video likely doesn't have captions enabled or they're not accessible. Please try a different video with captions enabled.",
                "start": 0,
                "duration": 10,
                "isUnavailableMessage": True
            }]