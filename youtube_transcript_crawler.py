# youtube_transcript_crawler.py
import asyncio
import json
import re
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

async def crawl_youtube_video(video_url):
    """
    Crawl a YouTube video page and attempt to extract the transcript.
    
    Args:
        video_url: URL of the YouTube video
    """
    print(f"Starting crawl of {video_url}...")
    
    # Validate YouTube URL
    if not is_valid_youtube_url(video_url):
        print("Error: Invalid YouTube URL. Please provide a valid YouTube video URL.")
        return None
    
    try:
        # Use a simpler browser config without wait_until
        browser_config = {
            "timeout": 60000,              # 60 second timeout
            "js_enabled": True             # Enable JavaScript
        }
        
        # Custom JavaScript to attempt to extract transcript data
        js_to_execute = """
        async function extractTranscript() {
            console.log("Attempting to extract YouTube transcript...");
            
            try {
                // Method 1: Check if transcript data is in the page source
                const htmlContent = document.documentElement.outerHTML;
                let transcriptData = [];
                
                // Look for transcript segments in the page
                const transcriptItems = document.querySelectorAll('ytd-transcript-segment-renderer');
                
                if (transcriptItems && transcriptItems.length > 0) {
                    console.log(`Found ${transcriptItems.length} transcript segments in the DOM`);
                    
                    // Extract text and timestamps from each segment
                    transcriptItems.forEach(item => {
                        const timeEl = item.querySelector('.segment-timestamp');
                        const textEl = item.querySelector('.segment-text');
                        
                        if (timeEl && textEl) {
                            transcriptData.push({
                                time: timeEl.textContent.trim(),
                                text: textEl.textContent.trim()
                            });
                        }
                    });
                } else {
                    console.log("No transcript segments found in the DOM");
                    
                    // Method 2: Try to find transcript button and click it
                    const moreActionsButton = document.querySelector('button[aria-label="More actions"]');
                    if (moreActionsButton) {
                        console.log("Found more actions button, clicking it");
                        moreActionsButton.click();
                        
                        // Wait for menu to appear
                        await new Promise(resolve => setTimeout(resolve, 1000));
                        
                        // Look for "Show transcript" menu item
                        const menuItems = document.querySelectorAll('tp-yt-paper-item, ytd-menu-service-item-renderer');
                        let foundTranscriptButton = false;
                        
                        for (const item of menuItems) {
                            const text = item.textContent.trim();
                            if (text.includes('transcript') || text.includes('Transcript')) {
                                console.log("Found show transcript option, clicking it");
                                item.click();
                                foundTranscriptButton = true;
                                
                                // Wait for transcript panel to load
                                await new Promise(resolve => setTimeout(resolve, 2000));
                                
                                // Now try to find transcript segments
                                const segments = document.querySelectorAll('ytd-transcript-segment-renderer');
                                console.log(`After clicking, found ${segments.length} transcript segments`);
                                
                                if (segments.length > 0) {
                                    segments.forEach(segment => {
                                        const timeEl = segment.querySelector('.segment-timestamp');
                                        const textEl = segment.querySelector('.segment-text');
                                        
                                        if (timeEl && textEl) {
                                            transcriptData.push({
                                                time: timeEl.textContent.trim(),
                                                text: textEl.textContent.trim()
                                            });
                                        }
                                    });
                                }
                                break;
                            }
                        }
                        
                        if (!foundTranscriptButton) {
                            console.log("Could not find the transcript option in the menu");
                        }
                    } else {
                        console.log("Could not find the more actions button");
                    }
                }
                
                // Method 3: Look for transcript data in the page source
                const transcriptPattern = /"playerCaptionsTracklistRenderer":(.+?)"captionTracks":(\\[\\{.+?\\}\\])/;
                const matches = htmlContent.match(transcriptPattern);
                
                if (matches && matches[1] && transcriptData.length === 0) {
                    console.log("Found potential transcript data in page source");
                    try {
                        const captionTracks = JSON.parse(matches[1]);
                        if (captionTracks && captionTracks.length > 0) {
                            // This only gives us the URL to the transcript, not the actual text
                            // We would need to make additional requests to get the full transcript
                            return { 
                                transcriptData,
                                captionTracks,
                                videoTitle: document.title,
                                videoId: new URLSearchParams(window.location.search).get('v')
                            };
                        }
                    } catch (e) {
                        console.log("Error parsing caption tracks:", e);
                    }
                }
                
                return { 
                    transcriptData,
                    videoTitle: document.title,
                    videoId: new URLSearchParams(window.location.search).get('v')
                };
            } catch (error) {
                console.error("Error in transcript extraction:", error);
                return { error: error.toString() };
            }
        }
        
        return await extractTranscript();
        """
        
        # Run the crawler
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(
                url=video_url,
                js_to_execute=js_to_execute,
                browser_config=browser_config,
                verbose=True
            )
            
            print("\n=== Crawl Completed ===")
            
            # Display basic information
            print(f"URL: {result.url}")
            
            # Check for custom data from JavaScript execution
            if hasattr(result, 'custom_data') and result.custom_data:
                print("\n=== Video Information ===")
                video_title = result.custom_data.get('videoTitle', 'Unknown title')
                video_id = result.custom_data.get('videoId', 'Unknown ID')
                print(f"Title: {video_title}")
                print(f"Video ID: {video_id}")
                
                # Check for transcript data
                transcript_data = result.custom_data.get('transcriptData', [])
                if transcript_data and len(transcript_data) > 0:
                    print(f"\n=== Transcript ({len(transcript_data)} segments) ===")
                    for i, segment in enumerate(transcript_data[:5]):  # Print first 5 segments
                        print(f"{segment.get('time', '??:??')} - {segment.get('text', 'No text')}")
                    if len(transcript_data) > 5:
                        print(f"... and {len(transcript_data) - 5} more segments")
                    
                    # Save transcript
                    save_transcript(video_id, video_title, transcript_data)
                else:
                    print("\nNo transcript data found in the page.")
                    
                    # Check if we have caption tracks
                    caption_tracks = result.custom_data.get('captionTracks', [])
                    if caption_tracks and len(caption_tracks) > 0:
                        print(f"\nFound {len(caption_tracks)} caption tracks, but could not extract direct transcript.")
                        for i, track in enumerate(caption_tracks):
                            base_url = track.get('baseUrl', 'No URL')
                            lang = track.get('languageCode', 'unknown')
                            print(f"Track {i+1}: Language {lang}")
            else:
                print("No custom data returned from JavaScript execution.")
            
            # Basic metadata
            if hasattr(result, 'metadata') and result.metadata:
                print("\n=== Page Metadata ===")
                for key in ['title', 'description', 'og:title', 'og:description']:
                    if key in result.metadata:
                        print(f"{key}: {result.metadata[key]}")
            
            return result
    
    except Exception as e:
        print(f"Error during crawling: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def is_valid_youtube_url(url):
    """Check if a URL is a valid YouTube video URL."""
    youtube_regex = r'^(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})'
    return re.match(youtube_regex, url) is not None

def save_transcript(video_id, video_title, transcript_data, output_file=None):
    """Save the transcript data to a file."""
    if not output_file:
        # Remove special characters from title for filename
        safe_title = re.sub(r'[^\w\s-]', '', video_title)
        safe_title = re.sub(r'[\s]+', '_', safe_title)
        output_file = f"transcript_{video_id}_{safe_title[:30]}.txt"
    
    try:
        # Save as text file
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"Transcript for: {video_title}\n")
            f.write(f"Video ID: {video_id}\n\n")
            
            for segment in transcript_data:
                f.write(f"{segment.get('time', '??:??')} - {segment.get('text', '')}\n")
        
        print(f"\nTranscript saved to {output_file}")
        
        # Also save as JSON
        json_file = output_file.replace(".txt", ".json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump({
                "videoId": video_id,
                "videoTitle": video_title,
                "transcript": transcript_data
            }, f, indent=2)
        
        print(f"Transcript also saved as JSON to {json_file}")
        
    except Exception as e:
        print(f"Error saving transcript: {str(e)}")

def main():
    """Run the crawler with command line arguments."""
    import argparse
    
    parser = argparse.ArgumentParser(description="YouTube Transcript Crawler")
    parser.add_argument("--url", required=True, help="YouTube video URL")
    parser.add_argument("--output", help="Output file for transcript (optional)")
    
    args = parser.parse_args()
    
    # Run the crawl
    result = asyncio.run(crawl_youtube_video(args.url))
    
    if result and hasattr(result, 'custom_data') and args.output:
        # Save with custom filename if provided
        transcript_data = result.custom_data.get('transcriptData', [])
        video_id = result.custom_data.get('videoId', 'unknown')
        video_title = result.custom_data.get('videoTitle', 'Untitled')
        save_transcript(video_id, video_title, transcript_data, args.output)

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python youtube_transcript_crawler.py --url YOUTUBE_URL [--output OUTPUT_FILE]")
        sys.exit(1)
    
    main()