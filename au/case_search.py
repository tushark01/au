async def case_search_main(page ,case_number):
    await page.locator('button[aria-label="Search"]').click()
    await page.get_by_role("searchbox", name="Search...").fill(case_number)

    await page.keyboard.press("Enter")
    await page.wait_for_timeout(5000)
    await page.locator("a", has_text=case_number).first.click()
    await page.wait_for_timeout(5000)

    return True


