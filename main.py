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
            # 1. Open the HubCloud initial landing page
            print(f"Navigating to initial landing page: {target_url}")
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            
            # 2. Check if it's HubCloud and click the dynamic download link generator button
            if "hubcloud" in target_url.lower():
                print("Clicking generation link wrapper...")
                generator_button = page.locator("text=Generate Direct Download Link").first
                await generator_button.wait_for(state="visible", timeout=15000)
                
                # Because clicking opens a new page/redirect tab, we handle and track the navigation hook
                async with context.expect_page(timeout=15000) as page_info:
                    await generator_button.click()
                
                # Switch active page context tracking focus to the newly opened tab (gamerxyt.com)
                page = await page_info.value
                print("Switched focus to dynamic redirect container page...")
            
            # 3. Wait for the new page layout to populate its DOM tree structure completely
            await page.wait_for_load_state("networkidle", timeout=20000)
            await page.wait_for_timeout(3000) # Safety buffer for slow-rendering dynamic scripts
            
            # 4. Scrape all the true server element items (FSL, FSLv2, 10Gbps, Buzz, etc.)
            server_elements = await page.query_selector_all("a")
            
            discovered_servers = []
            seen_urls = set()
            
            for element in server_elements:
                text = await element.inner_text()
                href = await element.get_attribute("href")
                
                if text and href:
                    text_clean = text.strip().replace("\n", " ")
                    href_lower = href.lower()
                    
                    # Filter out noise like utility layouts, admin views, or video tutorials
                    is_valid_server = any(keyword in text_clean.lower() for keyword in ["server", "download", "watch online"])
                    is_noise = any(keyword in href_lower for keyword in ["tinyurl", "telegram", "tutorial", "how-to", "/admin"])
                    
                    if is_valid_server and not is_noise:
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
                raise HTTPException(status_code=404, detail="Could not extract server links from the redirect target page layout.")
                
        except Exception as e:
            await browser.close()
            raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
