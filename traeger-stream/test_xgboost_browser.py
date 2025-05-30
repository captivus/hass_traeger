"""Test XGBoost temperature predictor in the browser using Playwright."""

import asyncio
from playwright.async_api import async_playwright

async def test_xgboost_dashboard():
    """Test the XGBoost implementation in the Streamlit dashboard."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        try:
            print('Opening Traeger dashboard at http://localhost:8501...')
            await page.goto('http://localhost:8501')
            
            # Wait for page to load
            await page.wait_for_timeout(5000)
            
            # Take initial screenshot
            await page.screenshot(path='dashboard_initial.png', full_page=True)
            print('Screenshot saved: dashboard_initial.png')
            
            # Check page title
            title = await page.title()
            print(f'Page title: {title}')
            
            # Look for temperature data
            page_content = await page.content()
            
            # Check for XGBoost predictor status
            if 'Collecting data' in page_content:
                print('XGBoost predictor is collecting training data')
                collecting_msgs = await page.query_selector_all('text=/Collecting data/')
                print(f'Found {len(collecting_msgs)} "Collecting data" messages')
            
            # Look for temperature readings
            temp_elements = await page.query_selector_all('text=/°F/')
            print(f'Found {len(temp_elements)} temperature readings on page')
            
            # Look for prediction messages
            if 'minutes' in page_content.lower() and ('target' in page_content.lower() or 'prediction' in page_content.lower()):
                print('Found temperature predictions!')
            elif 'XGBoost not installed' in page_content:
                print('ERROR: XGBoost not properly installed')
            elif 'Storage not available' in page_content:
                print('WARNING: Storage not available for XGBoost')
            
            # Check for error messages
            if 'Error' in page_content or 'error' in page_content:
                error_elements = await page.query_selector_all('[class*="error"], [class*="Error"]')
                print(f'Found {len(error_elements)} potential error elements')
            
            # Wait and check for live updates
            print('Waiting 15 seconds to observe live data updates...')
            await page.wait_for_timeout(15000)
            
            # Take final screenshot
            await page.screenshot(path='dashboard_final.png', full_page=True)
            print('Screenshot saved: dashboard_final.png')
            
            # Check final state
            final_content = await page.content()
            if 'Collecting data' in final_content:
                # Count data points
                import re
                data_points = re.findall(r'Collecting data\.\.\. \((\d+)/20 points\)', final_content)
                if data_points:
                    max_points = max([int(p) for p in data_points])
                    print(f'XGBoost has collected {max_points}/20 data points')
                else:
                    print('XGBoost is still in data collection phase')
            
            print('Test completed successfully!')
                
        except Exception as e:
            print(f'Error testing dashboard: {e}')
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_xgboost_dashboard())