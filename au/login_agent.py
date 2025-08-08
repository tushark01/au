from playwright.async_api import async_playwright

async def start_salesforce_session(username, password):
    playwright = await async_playwright().start()
    browser = playwright.chromium.launch(
    headless=False,
    channel="chrome"
    )
    context = await browser.new_context()
    page = await context.new_page()
    login_url = "https://uls-gfgc--uat.sandbox.lightning.force.com"
    await page.goto(login_url)
    await page.locator("#username").fill(username)   
    await page.wait_for_timeout(2000)

    await page.locator("#password").fill(password)
    await page.wait_for_timeout(2000)

    await page.locator("#Login").click()
    await page.wait_for_timeout(2000)

    return playwright, browser, context, page