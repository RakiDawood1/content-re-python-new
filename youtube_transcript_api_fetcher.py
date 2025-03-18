import re
import time
import random
from typing import List, Dict, Optional, Any
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled, CouldNotRetrieveTranscript
from youtube_transcript_api._errors import TooManyRequests

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
    
    def get_transcript_with_retry(self, video_id: str, language: str = 'en', max_retries: int = 3) -> List[Dict[str, Any]]:
        """
        Get transcript with exponential backoff retry logic
        
        Args:
            video_id: YouTube video ID
            language: Language code
            max_retries: Maximum number of retry attempts
            
        Returns:
            List of transcript segments
        """
        retry_count = 0
        last_error = None
        
        while retry_count < max_retries:
            try:
                # Get available transcripts
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                
                # Try to find the requested language
                try:
                    transcript = transcript_list.find_transcript([language])
                except NoTranscriptFound:
                    # If specific language not found, try to get English
                    print(f"Language {language} not found, trying English")
                    try:
                        transcript = transcript_list.find_transcript(['en'])
                    except NoTranscriptFound:
                        # If English also not available, get the first available transcript
                        print("English transcript not found, getting any available transcript")
                        available_transcripts = list(transcript_list._manually_created_transcripts.values())
                        if available_transcripts:
                            transcript = available_transcripts[0]
                        else:
                            # Try auto-generated transcripts
                            auto_transcripts = list(transcript_list._generated_transcripts.values())
                            if auto_transcripts:
                                transcript = auto_transcripts[0]
                            else:
                                raise NoTranscriptFound("No transcripts available")
                
                # Fetch the actual transcript
                data = transcript.fetch()
                
                # Convert to our expected format
                segments = []
                for item in data:
                    segments.append({
                        "text": item.get('text', ''),
                        "start": item.get('start', 0),
                        "duration": item.get('duration', 0)
                    })
                
                if segments:
                    print(f"Successfully retrieved {len(segments)} transcript segments")
                    return segments
                else:
                    raise Exception("Transcript was empty")
                
            except TooManyRequests as e:
                last_error = e
                retry_count += 1
                
                if retry_count < max_retries:
                    # Calculate backoff time: 2^retry * (0.5-1.5 seconds)
                    backoff = (2 ** retry_count) * (0.5 + random.random())
                    print(f"Hit rate limit, retrying in {backoff:.2f} seconds (attempt {retry_count}/{max_retries})")
                    time.sleep(backoff)
                else:
                    print(f"Max retries reached after rate limiting")
                    break
                    
            except (NoTranscriptFound, TranscriptsDisabled) as e:
                print(f"No transcript available: {e}")
                last_error = e
                break
                
            except Exception as e:
                print(f"Error fetching transcript: {e}")
                last_error = e
                retry_count += 1
                
                if retry_count < max_retries:
                    # Basic backoff for general errors
                    backoff = retry_count * 1.5
                    print(f"Retrying in {backoff:.2f} seconds (attempt {retry_count}/{max_retries})")
                    time.sleep(backoff)
                else:
                    print(f"Max retries reached")
                    break
        
        # If we got here, all attempts failed
        error_message = str(last_error) if last_error else "Unknown error"
        print(f"All attempts failed. Last error: {error_message}")
        
        # Return fallback message
        return [{
            "text": f"I'm sorry, the transcript for this video ({video_id}) is unavailable. The video likely doesn't have captions enabled, or YouTube's API rate limits were reached. Please try again later or try a different video.",
            "start": 0,
            "duration": 10,
            "isUnavailableMessage": True
        }]
    
    def get_transcript(self, video_id: str, language: str = 'en') -> List[Dict[str, Any]]:
        """
        Get transcript for a YouTube video using the youtube_transcript_api with retry logic
        
        Args:
            video_id: YouTube video ID
            language: Language code (default: 'en')
            
        Returns:
            List of transcript segments
        """
        print(f"Fetching transcript for video {video_id} in language {language}")
        
        # Use our retry logic for better handling of rate limits
        return self.get_transcript_with_retry(video_id, language)