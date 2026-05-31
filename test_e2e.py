import asyncio
from playwright.async_api import async_playwright
import os

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        print("1. Login as Admin")
        await page.goto("http://localhost:8000/login")
        await page.fill('input[name="username"]', "nsc.imp.atom@gmail.com")
        await page.fill('input[name="password"]', "admin12345!")
        await page.click('button:has-text("로그인")')
        await page.wait_for_url("**/room/general")
        await page.screenshot(path="test_results/1_login.png")
        print("Login successful")

        print("2. Test Phase 9: Admin Dashboard & Room Creation")
        await page.goto("http://localhost:8000/admin")
        await page.wait_for_selector('text=관리자 대시보드')
        
        # Room Creation Test
        await page.click('button:has-text("게시판 관리")')
        await page.wait_for_selector('input[placeholder="예: 가치투자방"]', state='visible')
        await page.fill('input[placeholder="예: 가치투자방"]', "가치투자방")
        await page.fill('input[placeholder="예: value-invest"]', "value-invest")
        await page.click('button:has-text("게시판 생성")')
        await asyncio.sleep(1)
        
        await page.screenshot(path="test_results/2_admin.png")
        print("Admin Dashboard loaded and room created")

        print("3. Test Phase 10: Events & Calendar")
        await page.goto("http://localhost:8000/room/general")
        await page.click('button:has-text("일정(Calendar)")')
        await page.wait_for_selector('text=새 일정 등록 (관리자)')
        await page.fill('input[placeholder="예: 2분기 실적 발표"]', "Playwright Test Event")
        await page.fill('input[type="datetime-local"]', "2026-12-31T10:00")
        await page.click('button:has-text("일정 등록")')
        await asyncio.sleep(1) # wait for toast/reload
        await page.screenshot(path="test_results/3_events.png")
        print("Event created")

        print("4. Test Phase 11: MyPage & Profile")
        await page.goto("http://localhost:8000/profile")
        await page.wait_for_selector('text=포인트 획득 내역')
        await page.click('button:has-text("프로필 수정")')
        await page.fill('textarea[placeholder="자신을 소개해주세요."]', "Hello I am the admin")
        await page.click('button:has-text("저장")')
        await asyncio.sleep(1)
        await page.click('button:has-text("나의 활동 (글/댓글)")')
        await page.screenshot(path="test_results/4_profile.png")
        print("Profile updated and activity viewed")

        print("5. Test Phase 12: Direct Messaging")
        await page.goto("http://localhost:8000/dm")
        await page.wait_for_selector('text=쪽지')
        await page.click('button:has-text("새 쪽지")')
        await page.wait_for_selector('text=새 쪽지 보내기')
        await page.screenshot(path="test_results/5_dm.png")
        print("DM page loaded and modal opened")

        await browser.close()

if __name__ == "__main__":
    os.makedirs("test_results", exist_ok=True)
    asyncio.run(run())
