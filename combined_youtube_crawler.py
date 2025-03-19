# combined_youtube_crawler.py
import asyncio
import json
import re
import sys
from crawl4ai import AsyncWebCrawler
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

async def crawl_youtube_with_api(video_url):
    """
    Crawl YouTube video metadata with crawl4ai and extract transcript with youtube-transcript-api.
    
    Args:
        video_url: URL of the YouTube video
    """
    print(f"Starting analysis of {video_url}...")
    
    # Extract video ID from URL
    video_id = extract_video_id(video_url)
    if not video_id:
        print("Error: Could not extract video ID from URL. Please provide a valid YouTube URL.")
        return None
    
    print(f"Video ID: {video_id}")
    
    # Create tasks for both crawling and transcript extraction
    metadata_task = crawl_for_metadata(video_url)
    transcript_task = extract_transcript(video_id)
    
    # Run both tasks
    metadata, transcript = await asyncio.gather(metadata_task, transcript_task)
    
    # Combine results
    result = {
        "video_id": video_id,
        "video_url": video_url,
        "metadata": metadata,
        "transcript": transcript
    }
    
    # Display summary
    display_results(result)
    
    # Save results
    save_results(result)
    
    return result

def extract_video_id(url):
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=([^&\s]+)',
        r'(?:https?:\/\/)?(?:www\.)?youtu\.be\/([^\?\s]+)',
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/embed\/([^\?\s]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None

async def crawl_for_metadata(video_url):
    """Use crawl4ai to extract metadata from YouTube video page."""
    print("Extracting video metadata with crawl4ai...")
    
    try:
        # Configure browser settings
        browser_config = {
            "timeout": 30000,  # 30 second timeout
            "js_enabled": True  # Enable JavaScript
        }
        
        # Run the crawler
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(
                url=video_url,
                browser_config=browser_config,
                verbose=True
            )
            
            # Extract metadata
            metadata = {}
            
            if hasattr(result, 'metadata') and result.metadata:
                # Copy relevant metadata
                for key in ['title', 'description', 'author', 'og:title', 'og:description', 
                            'og:image', 'og:video', 'og:video:tag']:
                    if key in result.metadata:
                        metadata[key] = result.metadata[key]
            
            # Extract more metadata from page content if available
            if hasattr(result, 'html') and result.html:
                # Try to extract channel name
                channel_match = re.search(r'"ownerChannelName":"([^"]+)"', result.html)
                if channel_match:
                    metadata['channel'] = channel_match.group(1)
                
                # Try to extract view count
                views_match = re.search(r'"viewCount":"(\d+)"', result.html)
                if views_match:
                    metadata['views'] = int(views_match.group(1))
                
                # Try to extract like count
                likes_match = re.search(r'"likeCount":"(\d+)"', result.html)
                if likes_match:
                    metadata['likes'] = int(likes_match.group(1))
                
                # Try to extract publish date
                date_match = re.search(r'"publishDate":"([^"]+)"', result.html)
                if date_match:
                    metadata['publish_date'] = date_match.group(1)
            
            print(f"Metadata extraction complete: {len(metadata)} fields found")
            return metadata
            
    except Exception as e:
        print(f"Error during metadata crawling: {str(e)}")
        return {}

async def extract_transcript(video_id):
    """Use youtube-transcript-api to extract transcript."""
    print("Extracting transcript with youtube-transcript-api...")
    
    # Create a coroutine to run the synchronous YouTube API in a separate thread
    async def get_transcript_async():
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, get_transcript, video_id)
    
    return await get_transcript_async()

def get_transcript(video_id):
    """Synchronous function to get transcript using youtube-transcript-api."""
    try:
        # Get available transcripts
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Try to get English transcript first
        try:
            transcript = transcript_list.find_transcript(['en'])
        except:
            # If English not available, get the first available transcript
            transcript = transcript_list.find_transcript([])
        
        # Get the actual transcript data
        transcript_data = transcript.fetch()
        print(f"Transcript found: {len(transcript_data)} segments, language: {transcript.language}")
        
        return {
            "success": True,
            "language": transcript.language,
            "is_generated": transcript.is_generated,
            "segments": transcript_data
        }
        
    except TranscriptsDisabled:
        print("Error: Transcripts are disabled for this video")
        return {
            "success": False,
            "error": "Transcripts are disabled for this video"
        }
        
    except NoTranscriptFound:
        print("Error: No transcript found for this video")
        return {
            "success": False,
            "error": "No transcript found for this video"
        }
        
    except Exception as e:
        print(f"Error extracting transcript: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

def display_results(result):
    """Display a summary of the results."""
    print("\n=== Video Information ===")
    print(f"Video ID: {result['video_id']}")
    print(f"URL: {result['video_url']}")
    
    # Display metadata
    if result['metadata']:
        print("\n=== Metadata ===")
        title = result['metadata'].get('title', result['metadata'].get('og:title', 'Unknown title'))
        print(f"Title: {title}")
        
        if 'channel' in result['metadata']:
            print(f"Channel: {result['metadata']['channel']}")
        
        if 'views' in result['metadata']:
            print(f"Views: {result['metadata']['views']:,}")
        
        if 'likes' in result['metadata']:
            print(f"Likes: {result['metadata']['likes']:,}")
        
        if 'publish_date' in result['metadata']:
            print(f"Published: {result['metadata']['publish_date']}")
    
    # Display transcript
    if result['transcript'] and result['transcript'].get('success', False):
        transcript_data = result['transcript']['segments']
        print(f"\n=== Transcript ({len(transcript_data)} segments) ===")
        print(f"Language: {result['transcript']['language']}")
        print(f"Generated: {'Yes' if result['transcript']['is_generated'] else 'No'}")
        
        # Show first 3 segments
        for i, segment in enumerate(transcript_data[:3]):
            print(f"{segment['start']:.2f}s: {segment['text']}")
        
        if len(transcript_data) > 3:
            print("...")
    else:
        if 'transcript' in result and 'error' in result['transcript']:
            print(f"\n=== Transcript Error ===\n{result['transcript']['error']}")
        else:
            print("\n=== No Transcript Data ===")

def save_results(result, prefix=None):
    """Save the results to files."""
    # Generate a filename prefix based on video ID
    if not prefix:
        video_id = result['video_id']
        prefix = f"youtube_{video_id}"
    
    # Save full JSON with all data
    json_file = f"{prefix}_data.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    
    print(f"\nFull data saved to {json_file}")
    
    # Save transcript to a separate text file if available
    if result['transcript'] and result['transcript'].get('success', False):
        transcript_data = result['transcript']['segments']
        txt_file = f"{prefix}_transcript.txt"
        
        with open(txt_file, "w", encoding="utf-8") as f:
            # Add header with metadata
            title = result['metadata'].get('title', result['metadata'].get('og:title', 'Unknown title'))
            f.write(f"Transcript for: {title}\n")
            f.write(f"Video ID: {result['video_id']}\n")
            f.write(f"Language: {result['transcript']['language']}\n")
            f.write(f"Generated: {'Yes' if result['transcript']['is_generated'] else 'No'}\n\n")
            
            # Write transcript segments
            for segment in transcript_data:
                f.write(f"[{segment['start']:.2f}s - {segment['start'] + segment['duration']:.2f}s] {segment['text']}\n")
        
        print(f"Transcript saved to {txt_file}")

def main():
    """Run the crawler with command line arguments."""
    import argparse
    
    parser = argparse.ArgumentParser(description="YouTube Crawler with Transcript API")
    parser.add_argument("--url", required=True, help="YouTube video URL")
    parser.add_argument("--output", help="Output file prefix (optional)")
    
    args = parser.parse_args()
    
    # Run the combined crawler
    result = asyncio.run(crawl_youtube_with_api(args.url))
    
    if result and args.output:
        # Save with custom filename prefix if provided
        save_results(result, args.output)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python combined_youtube_crawler.py --url YOUTUBE_URL [--output OUTPUT_PREFIX]")
        sys.exit(1)
    
    main()