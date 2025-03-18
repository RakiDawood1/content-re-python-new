# youtube_transcript_crawler.py
import re
import asyncio
from typing import List, Dict, Optional, Any
from crawl4ai import AsyncWebCrawler

class YouTubeTranscriptCrawler:
    """A YouTube transcript extractor using the open-source crawl4ai library."""
    
    def extract_video_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from various URL formats."""
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
    
    async def get_transcript_async(self, video_id_or_url: str) -> List[Dict[str, Any]]:
        """Asynchronously get transcript for a YouTube video using crawl4ai."""
        # Determine if input is a video ID or URL
        if len(video_id_or_url) == 11 and re.match(r'^[A-Za-z0-9_-]{11}$', video_id_or_url):
            video_id = video_id_or_url
        else:
            video_id = self.extract_video_id(video_id_or_url)
            if not video_id:
                return self._error_response("Invalid YouTube URL or video ID")
        
        # Construct the YouTube URL
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        
        try:
            # Create crawler instance
            async with AsyncWebCrawler() as crawler:
                # Create browser configuration parameters
                browser_config = {
                    "wait_for_selector": ".html5-video-container",  # Wait for video player to appear
                    "timeout": 60000,  # 60 seconds timeout
                    "wait_until": "networkidle2",  # Wait until network is idle
                    "js_enabled": True,  # JavaScript must be enabled
                    "block_images": True,  # Block images to save bandwidth
                    "block_css": False,  # Keep CSS for caption styling
                    "block_fonts": True,  # Block fonts to save bandwidth
                    "stealth_mode": True  # Use stealth mode to avoid detection
                }
                
                # Create extraction script for captions
                extraction_js = self._get_extraction_script()
                
                # Run the crawler with custom extraction script
                result = await crawler.arun(
                    url=youtube_url,
                    browser_config=browser_config,  # Using browser_config instead of BrowserParams
                    js_to_execute=extraction_js,
                    extract_text=False,  # We'll use our custom extraction instead
                    extract_metadata=True
                )
                
                # Check if extraction was successful
                if not result or not hasattr(result, 'custom_data') or not result.custom_data:
                    return self._error_response(f"Failed to extract transcript from {youtube_url}")
                
                # Parse the transcript data from custom_data
                transcript_data = result.custom_data.get('transcript', [])
                
                if not transcript_data:
                    return self._error_response(f"No transcript found for video {video_id}")
                
                # Return the transcript segments
                return transcript_data
                
        except Exception as e:
            return self._error_response(f"Error fetching transcript: {str(e)}")
    
    def get_transcript(self, video_id_or_url: str) -> List[Dict[str, Any]]:
        """Synchronous wrapper for get_transcript_async."""
        return asyncio.run(self.get_transcript_async(video_id_or_url))
    
    def _get_extraction_script(self) -> str:
        """Get the JavaScript code to extract captions from YouTube."""
        return """
        async function customExtract() {
            console.log("Starting YouTube transcript extraction");
            
            try {
                // Wait for the video player to load
                await page.waitForSelector('.html5-video-container', { timeout: 15000 });
                console.log("Video player detected");
                
                // Try to find captions by checking if subtitles button exists
                const subtitleButton = await page.$('.ytp-subtitles-button');
                let captionsEnabled = false;
                
                if (subtitleButton) {
                    console.log("Subtitles button found");
                    
                    // Check if captions are already enabled (button has aria-pressed="true")
                    const isPressed = await subtitleButton.evaluate(el => el.getAttribute('aria-pressed'));
                    captionsEnabled = isPressed === 'true';
                    
                    if (!captionsEnabled) {
                        // Enable captions by clicking the button
                        console.log("Enabling captions...");
                        await subtitleButton.click();
                        await page.waitForTimeout(2000); // Wait for captions to appear
                        captionsEnabled = true;
                    } else {
                        console.log("Captions already enabled");
                    }
                } else {
                    console.log("No subtitles button found - captions may not be available");
                }
                
                // Start the video if it's not playing
                const videoElement = await page.$('.html5-main-video');
                if (videoElement) {
                    const isPlaying = await videoElement.evaluate(video => !video.paused);
                    if (!isPlaying) {
                        console.log("Starting video playback");
                        await page.click('.ytp-play-button');
                        await page.waitForTimeout(1000);
                    }
                }
                
                // Extract captions
                console.log("Collecting transcript...");
                let transcript = [];
                let captionTexts = new Set(); // To track unique captions
                
                // Function to extract caption text
                const extractCaptions = async () => {
                    const currentTime = await videoElement.evaluate(video => video.currentTime);
                    const captionSegments = await page.$$('.ytp-caption-segment');
                    
                    if (captionSegments.length > 0) {
                        let currentTextLine = "";
                        for (const segment of captionSegments) {
                            const text = await segment.evaluate(el => el.textContent);
                            currentTextLine += text + " ";
                        }
                        
                        currentTextLine = currentTextLine.trim();
                        
                        if (currentTextLine && !captionTexts.has(currentTextLine)) {
                            captionTexts.add(currentTextLine);
                            transcript.push({
                                text: currentTextLine,
                                start: currentTime,
                                duration: 2.0 // Approximate duration
                            });
                        }
                    }
                };
                
                // Fast forward through the video to collect more captions
                for (let i = 0; i < 20; i++) {
                    await extractCaptions();
                    
                    // Jump forward in video to capture more captions
                    if (i % 2 === 0) {
                        await videoElement.evaluate(video => {
                            video.currentTime = video.currentTime + 10;
                        });
                    }
                    
                    await page.waitForTimeout(1000);
                    
                    // If we have collected enough captions, stop
                    if (transcript.length >= 15) {
                        break;
                    }
                }
                
                // Calculate durations based on consecutive start times
                for (let i = 0; i < transcript.length - 1; i++) {
                    transcript[i].duration = transcript[i+1].start - transcript[i].start;
                }
                
                return { transcript };
                
            } catch (error) {
                console.error("Error during extraction:", error.message);
                return { 
                    error: error.message,
                    transcript: []
                };
            }
        }
        
        return await customExtract();
        """
    
    def _error_response(self, message: str) -> List[Dict[str, Any]]:
        """Create a standardized error response."""
        return [{
            "text": message,
            "start": 0,
            "duration": 0,
            "error": True
        }]