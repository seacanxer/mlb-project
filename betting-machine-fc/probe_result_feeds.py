import asyncio
import sys
sys.path.insert(0, "/home/ubuntu/mlb-project/betting-machine-fc")
from scraper_flashscore import fetch_feed, parse_feed

async def main():
    tests = [
        ("f_1_0_3_en_1", "https://global.flashscore.ninja/2/x/feed/f_1_0_3_en_1"),
        ("cf_1_76_8_en_y_1", "https://global.flashscore.ninja/2/x/feed/cf_1_76_8_en_y_1"),
        ("f_1_76_8_en_y_1", "https://global.flashscore.ninja/2/x/feed/f_1_76_8_en_y_1"),
        ("c_1_76_8_en_y_1", "https://global.flashscore.ninja/2/x/feed/c_1_76_8_en_y_1"),
        ("c_1_8_en_y_1", "https://global.flashscore.ninja/2/x/feed/c_1_8_en_y_1"),
    ]
    for name, url in tests:
        try:
            body = await fetch_feed(url)
            if not body:
                print(f"{name}: EMPTY")
                continue
            if name == "f_1_0_3_en_1":
                print(f"{name}: {len(body)} chars")
                print("  HEAD:", body[:400].replace('\n', ' '))
                continue
            parsed = parse_feed(body)
            count = sum(1 for k in parsed if k.startswith("AA") and parsed[k])
            print(f"{name}: {len(body)} chars, {count} matches")
            for key, val in list(parsed.items()):
                if key.startswith("AA") and val:
                    print("  SAMPLE:", val[:300])
                    break
            if not count:
                print("  HEAD:", body[:300].replace('\n', ' '))
        except Exception as e:
            print(f"{name}: ERROR {e}")

asyncio.run(main())