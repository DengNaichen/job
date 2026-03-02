import zipfile
from pathlib import Path

import httpx

from app.core.config import get_settings

GEONAMES_URL = "https://download.geonames.org/export/dump/"
FILES = ["cities15000.zip", "admin1CodesASCII.txt", "countryInfo.txt"]


async def download_file(client: httpx.AsyncClient, url: str, dest: Path):
    print(f"Downloading {url} to {dest}...")
    async with client.stream("GET", url) as response:
        response.raise_for_status()
        with open(dest, "wb") as f:
            async for chunk in response.aiter_bytes():
                f.write(chunk)


async def main():
    settings = get_settings()
    data_dir = Path(settings.geonames_data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=60.0) as client:
        for filename in FILES:
            dest = data_dir / filename
            if not dest.exists():
                await download_file(client, GEONAMES_URL + filename, dest)
                if filename.endswith(".zip"):
                    print(f"Unzipping {dest}...")
                    with zipfile.ZipFile(dest, "r") as zip_ref:
                        zip_ref.extractall(data_dir)
            else:
                print(f"{filename} already exists.")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
