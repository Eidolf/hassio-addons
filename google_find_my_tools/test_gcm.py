
import asyncio
import aiohttp
import json
from base64 import b64encode
import secrets
import logging

# Config
API_KEY = "AIzaSyD_gko3P392v6how2H7UpdeXQ0v2HLettc"
PROJECT_ID = "google.com:api-project-289722593072"
APP_ID = "1:289722593072:android:3cfcf5bc359f0308"
FCM_INSTALLATION = "https://firebaseinstallations.googleapis.com/v1/"

# Certs to try
CERTS = [
    "7934664F8684277765D0A1384077651817757361", # The one I tried
    "3B:C3:68:1C:12:41:88:81:64:18:7C:E6:9E:01:3E:69:21:46:11:0B", # Common Google cert
    "58:E1:C4:13:3F:74:41:EC:3D:2C:27:02:70:BE:53:15:ED:13:F9:69", # Facebook?
]

async def try_register(package, cert):
    print(f"Trying Package: {package}, Cert: {cert}")
    
    fid = bytearray(secrets.token_bytes(17))
    fid[0] = 0b01110000 + (fid[0] % 0b00010000)
    fid64 = b64encode(fid).decode()

    hb_header = b64encode(json.dumps({"heartbeats": [], "version": 2}).encode()).decode()
    
    headers = {
        "x-firebase-client": hb_header,
        "x-goog-api-key": API_KEY,
        "X-Android-Package": package,
        "X-Android-Cert": cert.replace(":", "") if cert else None
    }
    # Remove None headers
    headers = {k: v for k, v in headers.items() if v is not None}

    payload = {
        "appId": APP_ID,
        "authVersion": "FIS_v2",
        "fid": fid64,
        "sdkVersion": "w:0.6.6",
    }
    url = FCM_INSTALLATION + f"projects/{PROJECT_ID}/installations"
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            text = await resp.text()
            if resp.status == 200:
                print(f"SUCCESS! Token: {text[:50]}...")
                return True
            else:
                print(f"FAILED ({resp.status}): {text}")
                return False

async def main():
    # Try 1: No headers (Baseline)
    # await try_register(None, None)

    # Try 2: com.google.android.apps.adm + Certs
    for cert in CERTS:
        if await try_register("com.google.android.apps.adm", cert):
            break
            
if __name__ == "__main__":
    asyncio.run(main())
