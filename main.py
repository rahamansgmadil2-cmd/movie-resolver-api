import os
import asyncio
import urllib.parse
from fastapi import FastAPI, HTTPException
from playwright.async_api import async_playwright

app = FastAPI()

# Strict list of tracking and popunder domains to close instantly
BAD_DOMAINS = [
    "canatrace.com", "doubleclick.net", "adsystem", "popads", "click?", 
    "adsterra", "exoclick", "onclickads", "juicyads", "a-ads", "youtube.com"
]

async def route_intercept(route):
    """Aborts telemetry/ad network connections early at the gate"""
    url = route.request.url.lower()
    if any(domain in url for domain in BAD_DOMAINS):
        await route.abort()
    else:
        await route.continue_()

def clear_malicious_popups(context, valid_keywords):
    """Scans all open tabs, kills ad popups, returns the genuine target window"""
    main_active_page = None
    for p_tab in context.pages:
        tab_url = p_tab.url.lower()
        if any(ad_dom in tab_url for ad_dom in BAD_DOMAINS):
            print(f"Terminated background ad tab: {p_tab.url}")
            p_tab.close()
        elif any(kw in tab_url for kw in valid_keywords):
            main_active_page = p_tab
    return main_active_page

@app.get("/get-all-qualities")
async def get_all_qualities(movie_name: str):
    """
    Stage 1: Searches the movie, navigates past the homepage banners,
    and returns an exhaustive array list of every quality resolution link found.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.route("**/*", route_intercept)
        
        valid_trackers = ["hdhub4u", "greenmotors", "hblinks", "hubcloud"]
        
        try:
            # 1. Access the main landing zone portal
            print("Accessing root web extension...")
            await page.goto("https://hdhub4u.fans", wait_until="domcontentloaded", timeout=30000)
            
            view_site_btn = page.locator("text=View Full Site").first
            if await view_site_btn.is_visible():
                await view_site_btn.click()
                await page.wait_for_timeout(3000)
                page = clear_malicious_popups(context, valid_trackers) or page

            # Dismiss modal layout announcements if visible
            dismiss_btn = page.locator("text=Dismiss").first
            if await dismiss_btn.is_visible():
                await dismiss_btn.click()

            # 2. Trigger Search Workflow
            print(f"Searching index parameters for: {movie_name}")
            search_query = urllib.parse.quote(movie_name)
            target_search_url = f"{page.url.rstrip('/')}/search/{search_query}"
            
            await page.goto(target_search_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            page = clear_malicious_popups(context, valid_trackers) or page

            # Isolate the exact matching movie information card link
            movie_link = page.locator(f"a:has-text('{movie_name}')").first
            if not await movie_link.is_visible():
                movie_link = page.locator(".post-title a, .thumb sequential a").first
                
            if not await movie_link.is_visible():
                raise HTTPException(status_code=404, detail="The requested title could not be matched in results.")
                
            await movie_link.click()
            await page.wait_for_timeout(4000)
            page = clear_malicious_popups(context, valid_trackers) or page

            # 3. Scrape ALL available download elements grouped inside the post layout block
            print("Parsing movie specs template layout...")
            all_anchors = await page.query_selector_all("a")
            
            extracted_qualities = []
            seen_urls = set()
            
            for anchor in all_anchors:
                text = await anchor.inner_text()
                href = await anchor.get_attribute("href")
                
                if text and href:
                    text_clean = text.strip().replace("\n", " ")
                    # Filter anchors containing resolution metrics (e.g., 480p, 720p, 1080p, HEVC, HQ-Rip)
                    is_quality_node = any(metric in text_clean.lower() for metric in ["480p", "720p", "1080p", "hevc", "hq-rip", "x264"])
                    
                    if is_quality_node and href not in seen_urls and href.startswith("http"):
                        seen_urls.add(href)
                        extracted_qualities.append({
                            "quality_title": text_clean,      # e.g., "1080p HEVC [2.3GB]"
                            "mediator_target_url": href       # The unique gateway path link for this quality
                        })

            await browser.close()
            
            if extracted_qualities:
                return {
                    "status": "success",
                    "movie": movie_name,
                    "total_options_found": len(extracted_qualities),
                    "options": extracted_qualities
                }
            else:
                raise HTTPException(status_code=404, detail="No resolution selection fields isolated from page layout.")
                
        except Exception as e:
            await browser.close()
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/bypass-gate")
async def bypass_gate(mediator_url: str):
    """
    Stage 2: Takes the selected quality link chosen by the user,
    navigates through the verification countdown sheets, and returns the final file server link list.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.route("**/*", route_intercept)
        valid_trackers = ["greenmotors", "hblinks", "hubcloud", "gamerxyt", "hubdrive"]
        
        try:
            print(f"Opening selected quality block: {mediator_url}")
            await page.goto(mediator_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            page = clear_malicious_popups(context, valid_trackers) or page

            # Bypassing the verification layers
            continue_btn = page.locator("text=CLICK TO CONTINUE, text=Continue").first
            await continue_btn.wait_for(state="visible", timeout=15000)
            await continue_btn.click()
            
            get_links_btn = page.locator("text=GET LINKS, text=Get Link").first
            await get_links_btn.wait_for(state="visible", timeout=25000)
            await get_links_btn.click()
            await page.wait_for_timeout(5000)
            page = clear_malicious_popups(context, valid_trackers) or page

            # Inside HubLinks page layout. Extracting target links.
            print("Parsing core download servers matrix...")
            await page.wait_for_load_state("networkidle")
            
            server_elements = await page.query_selector_all("a")
            discovered_servers = []
            seen_urls = set()
            
            for element in server_elements:
                text = await element.inner_text()
                href = await element.get_attribute("href")
                
                if text and href:
                    text_clean = text.strip().replace("\n", " ")
                    href_lower = href.lower()
                    
                    is_valid_server = any(kw in text_clean.lower() for kw in ["server", "download", "watch online", "gbps", "hubcloud", "hubdrive"])
                    is_noise = any(kw in href_lower for kw in ["tinyurl", "telegram", "tutorial", "how-to", "/admin"])
                    
                    if is_valid_server and not is_noise:
                        if href not in seen_urls:
                            seen_urls.add(href)
                            discovered_servers.append({
                                "server_name": text_clean,
                                "target_link": href
                            })
            
            await browser.close()
            return {"status": "success", "servers": discovered_servers}
            
        except Exception as e:
            await browser.close()
            raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
