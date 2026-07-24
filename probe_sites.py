from playwright.sync_api import sync_playwright

urls = [
    'https://www.ticketmaster.com/league-of-legends-world-championships-brooklyn-new-york-11-14-2026/event/300064EA0334EE28?referrer=https%3A%2F%2Fwww.ticketmaster.com%2Fleague-of-legends-world-championships-tickets%2Fartist%2F1906735',
    'https://www.stubhub.com/league-of-legends-world-championship-brooklyn-tickets-11-14-2026/event/161251368/?backUrl=%2Fleague-of-legends-world-championship-tickets%2Fgrouping%2F150363310&lt=45.791&lg=-122.529&quantity=1',
    'https://seatgeek.com/league-of-legends-tickets/esports/2026-11-14-12-pm/18390890?quantity=1',
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for url in urls:
        page = browser.new_page()
        print('URL:', url)
        try:
            page.goto(url, wait_until='networkidle', timeout=60000)
            print('Title:', page.title())
            text = page.locator('body').inner_text(timeout=10000)
            print(text[:6000])
        except Exception as e:
            print('ERR', e)
        print('---')
    browser.close()
