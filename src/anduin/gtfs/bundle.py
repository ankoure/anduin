import os
import zipfile
import tempfile
import shutil
from pathlib import Path
from urllib.request import urlretrieve


class GTFSBundleManager:
    """Manages downloading and extracting GTFS bundles."""

    DEFAULT_URL = "https://cdn.mbta.com/MBTA_GTFS.zip"

    def __init__(self, url: str | None = None, extract_dir: str | None = None):
        """
        Initialize the GTFS bundle manager.

        :param url: URL to download the GTFS bundle from. Defaults to MBTA GTFS feed.
        :param extract_dir: Directory to extract files to. Defaults to ./data/gtfs.
        """
        self.url = url or self.DEFAULT_URL
        self.extract_dir = Path(extract_dir) if extract_dir else Path("data/gtfs")

    def download(self, dest_path: str | Path | None = None) -> Path:
        """
        Download the GTFS bundle.

        :param dest_path: Destination path for the zip file. If None, uses a temp file.
        :returns: Path to the downloaded zip file.
        """
        if dest_path is None:
            fd, dest_path = tempfile.mkstemp(suffix=".zip")
            os.close(fd)

        dest_path = Path(dest_path)
        urlretrieve(self.url, dest_path)
        return dest_path

    def extract(self, zip_path: str | Path) -> Path:
        """
        Extract a GTFS zip file.

        :param zip_path: Path to the GTFS zip file.
        :returns: Path to the extraction directory.
        """
        zip_path = Path(zip_path)
        self.extract_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(self.extract_dir)

        return self.extract_dir

    def download_and_extract(self, keep_zip: bool = False) -> Path:
        """
        Download and extract the GTFS bundle in one step.

        :param keep_zip: If True, keeps the downloaded zip file in extract_dir.
        :returns: Path to the extraction directory.
        """
        zip_path = self.download()

        try:
            self.extract(zip_path)
        finally:
            if keep_zip:
                final_zip = self.extract_dir / "gtfs.zip"
                shutil.move(str(zip_path), str(final_zip))
            else:
                zip_path.unlink(missing_ok=True)

        return self.extract_dir

    def cleanup(self) -> None:
        """Remove the extracted GTFS data directory."""
        if self.extract_dir.exists():
            shutil.rmtree(self.extract_dir)
