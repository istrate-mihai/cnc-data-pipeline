import subprocess
import requests
import time


def test_api():
    urls = [
        ("Dashboard", "http://localhost:8000/"),
        ("Measurements", "http://localhost:8000/api/measurements?limit=5"),
        ("Stats", "http://localhost:8000/api/stats"),
        ("FMEA", "http://localhost:8000/api/fmea"),
    ]
    for name, url in urls:
        try:
            r = requests.get(url, timeout=3)
            print(f"✅ {name}: {r.status_code}")
        except Exception as e:
            print(f"❌ {name}: {e}")


if __name__ == "__main__":
    print("Testing local endpoints...")
    time.sleep(1)
    test_api()
