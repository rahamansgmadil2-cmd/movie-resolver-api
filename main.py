import os
import asyncio
from fastapi import FastAPI, HTTPException
from playwright.async_api import async_playwright

app = FastAPI()

BLOCKED_DOMAINS = [
    "doubleclick.net", "adsystem", "popads", "adsterra", "exoclick", 
    "onclickads", "juicyads", "a-ads"
]

async def route_intercept(route):
    url = route.request.url.lower()
    if any(domain in url for domain in BLOCKED_DOMAINS):
        await route.abort()
    else:
        await route.continue_()

@app.get("/resolve")
async def resolve_movie_stream(target_url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.route("**/*", route_intercept)
        
        try:
            # 1. Open the target webpage
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            
            # 2. Check if it's a HubCloud landing page requiring generation
            if "hubcloud" in target_url.lower():
                print("Processing HubCloud landing layer...")
                generator_button = page.locator("text=Generate Direct Download Link").first
                if await generator_button.is_visible():
                    await generator_button.click()
                    # Wait for the intermediate mediator page (e.g., gamerxyt.com) to load its elements
                    await page.wait_for_load_state("networkidle")
            
            # 3. Scrape all available server download links on the current page view
            # This selector matches buttons containing download server patterns
            server_elements = await page.query_selector_all("a[href*='drive'], a[href*='file'], a:has-text('Download'), a:has-text('Server')")
            
            discovered_servers = []
            seen_urls = set()
            
            for element in server_elements:
                text = await element.inner_text()
                href = await element.get_attribute("href")
                
                # Clean up and filter out empty text, telegram links, or duplicates
                text_clean = text.strip().replace("\n", " ")
                if href and text_clean and "telegram" not in href.lower() and "android app" not in href.lower():
                    if href not in seen_urls:
                        seen_urls.add(href)
                        discovered_servers.append({
                            "server_name": text_clean,
                            "target_link": href
                        })
            
            await browser.close()
            
            if discovered_servers:
                return {
                    "status": "success",
                    "total_servers_found": len(discovered_servers),
                    "servers": discovered_servers
                }
            else:
                raise HTTPException(status_code=404, detail="No active server download links could be parsed from the page template.")
                
        except Exception as e:
            await browser.close()
            raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
