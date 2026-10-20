import os
import re
import asyncio
from fastapi import FastAPI, HTTPException
from playwright.async_api import async_playwright

app = FastAPI()

# A list of common third-party ad/tracking domains to block instantly
BLOCKED_DOMAINS = [
    "doubleclick.net", "adsystem", "onclickads", "popads", 
    "exoclick", "juicyads", "adsterra", "a-ads"
]

async def route_intercept(route):
    """Blocks ad tracking requests to prevent popups and speed up loading"""
    url = route.request.url.lower()
    if any(domain in url for domain in BLOCKED_DOMAINS):
        await route.abort()
    else:
        await route.continue_()

@app.get("/resolve")
async def resolve_movie_stream(target_url: str):
    """
    Accepts a direct link to a file hoster (e.g. HubCloud link retrieved from HDHub4u)
    and extracts the final playback media link (.mp4/.m3u8).
    """
    async with async_playwright() as p:
        # Launch background browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        page = await context.new_page()
        
        # Apply the global network ad-blocker
        await page.route("**/*", route_intercept)
        
        final_video_url = None
        
        # Monitor all background responses to catch the raw stream file
        async def intercept_response(response):
            nonlocal final_video_url
            url = response.url.lower()
            content_type = response.headers.get("content-type", "").lower()
            
            # Catch direct file links or HLS playlists
            if "video" in content_type or ".mp4" in url or ".m3u8" in url or "googlevideo" in url:
                final_video_url = response.url

        page.on("response", intercept_response)

        try:
            # 1. Navigate to the file hoster landing page
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            
            # 2. Automatically look for the standard play/watch button layout
            # These selectors match standard hoster nodes (Watch Online, Stream, Proceed)
            button_selectors = [
                "text=Watch Online", "text=Stream", "text=Proceed to Video",
                "button:has-text('Play')", "a:has-text('Watch')"
            ]
            
            button_found = False
            for selector in button_selectors:
                element = page.locator(selector).first
                if await element.is_visible():
                    await element.click()
                    button_found = True
                    break
                    
            # 3. Wait a few moments for the player to initialize and stream data
            await page.wait_for_timeout(4000)
            await browser.close()
            
            if final_video_url:
                return {"status": "success", "stream_url": final_video_url}
            else:
                raise HTTPException(status_code=404, detail="Direct video stream could not be captured.")
                
        except Exception as e:
            await browser.close()
            raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
