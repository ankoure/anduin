import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from anduin.gtfs.bundle import GTFSBundleManager


@pytest.fixture
def temp_extract_dir(tmp_path):
    """Provide a temporary directory for extraction."""
    return tmp_path / "gtfs_extract"


@pytest.fixture
def sample_gtfs_zip(tmp_path):
    """Create a sample GTFS zip file for testing."""
    zip_path = tmp_path / "sample_gtfs.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("stops.txt", "stop_id,stop_name\n1,Test Stop")
        zf.writestr("routes.txt", "route_id,route_name\n1,Test Route")
        zf.writestr("trips.txt", "trip_id,route_id\n1,1")
    return zip_path


class TestGTFSBundleManagerInit:
    """Tests for GTFSBundleManager initialization."""

    def test_default_url(self):
        """Should use MBTA GTFS URL by default."""
        manager = GTFSBundleManager()
        assert manager.url == "https://cdn.mbta.com/MBTA_GTFS.zip"

    def test_custom_url(self):
        """Should accept a custom URL."""
        custom_url = "https://example.com/gtfs.zip"
        manager = GTFSBundleManager(url=custom_url)
        assert manager.url == custom_url

    def test_default_extract_dir(self):
        """Should use data/gtfs as default extraction directory."""
        manager = GTFSBundleManager()
        assert manager.extract_dir == Path("data/gtfs")

    def test_custom_extract_dir(self):
        """Should accept a custom extraction directory."""
        manager = GTFSBundleManager(extract_dir="/custom/path")
        assert manager.extract_dir == Path("/custom/path")

    def test_custom_extract_dir_as_string(self, temp_extract_dir):
        """Should convert string extract_dir to Path."""
        manager = GTFSBundleManager(extract_dir=str(temp_extract_dir))
        assert isinstance(manager.extract_dir, Path)
        assert manager.extract_dir == temp_extract_dir


class TestGTFSBundleManagerDownload:
    """Tests for GTFSBundleManager.download()."""

    @patch("anduin.gtfs.bundle.urlretrieve")
    def test_download_to_temp_file(self, mock_urlretrieve):
        """Should download to a temp file when no dest_path is provided."""
        manager = GTFSBundleManager()
        result = manager.download()

        assert result.suffix == ".zip"
        mock_urlretrieve.assert_called_once()
        call_args = mock_urlretrieve.call_args
        assert call_args[0][0] == manager.url

        # Clean up the temp file
        result.unlink(missing_ok=True)

    @patch("anduin.gtfs.bundle.urlretrieve")
    def test_download_to_specified_path(self, mock_urlretrieve, tmp_path):
        """Should download to the specified destination path."""
        dest_path = tmp_path / "downloaded.zip"
        manager = GTFSBundleManager()
        result = manager.download(dest_path=dest_path)

        assert result == dest_path
        mock_urlretrieve.assert_called_once_with(manager.url, dest_path)

    @patch("anduin.gtfs.bundle.urlretrieve")
    def test_download_with_string_path(self, mock_urlretrieve, tmp_path):
        """Should accept string path and convert to Path."""
        dest_path = str(tmp_path / "downloaded.zip")
        manager = GTFSBundleManager()
        result = manager.download(dest_path=dest_path)

        assert isinstance(result, Path)
        assert result == Path(dest_path)

    @patch("anduin.gtfs.bundle.urlretrieve")
    def test_download_uses_configured_url(self, mock_urlretrieve, tmp_path):
        """Should download from the configured URL."""
        custom_url = "https://custom.example.com/feed.zip"
        manager = GTFSBundleManager(url=custom_url)
        dest_path = tmp_path / "test.zip"

        manager.download(dest_path=dest_path)

        mock_urlretrieve.assert_called_once_with(custom_url, dest_path)


class TestGTFSBundleManagerExtract:
    """Tests for GTFSBundleManager.extract()."""

    def test_extract_creates_directory(self, sample_gtfs_zip, temp_extract_dir):
        """Should create the extraction directory if it doesn't exist."""
        manager = GTFSBundleManager(extract_dir=str(temp_extract_dir))
        assert not temp_extract_dir.exists()

        manager.extract(sample_gtfs_zip)

        assert temp_extract_dir.exists()
        assert temp_extract_dir.is_dir()

    def test_extract_extracts_files(self, sample_gtfs_zip, temp_extract_dir):
        """Should extract all files from the zip."""
        manager = GTFSBundleManager(extract_dir=str(temp_extract_dir))
        manager.extract(sample_gtfs_zip)

        assert (temp_extract_dir / "stops.txt").exists()
        assert (temp_extract_dir / "routes.txt").exists()
        assert (temp_extract_dir / "trips.txt").exists()

    def test_extract_file_contents(self, sample_gtfs_zip, temp_extract_dir):
        """Should preserve file contents during extraction."""
        manager = GTFSBundleManager(extract_dir=str(temp_extract_dir))
        manager.extract(sample_gtfs_zip)

        stops_content = (temp_extract_dir / "stops.txt").read_text()
        assert "stop_id,stop_name" in stops_content
        assert "1,Test Stop" in stops_content

    def test_extract_returns_extract_dir(self, sample_gtfs_zip, temp_extract_dir):
        """Should return the extraction directory path."""
        manager = GTFSBundleManager(extract_dir=str(temp_extract_dir))
        result = manager.extract(sample_gtfs_zip)

        assert result == temp_extract_dir

    def test_extract_accepts_string_path(self, sample_gtfs_zip, temp_extract_dir):
        """Should accept string path for zip file."""
        manager = GTFSBundleManager(extract_dir=str(temp_extract_dir))
        result = manager.extract(str(sample_gtfs_zip))

        assert result == temp_extract_dir
        assert (temp_extract_dir / "stops.txt").exists()

    def test_extract_creates_nested_directories(self, tmp_path):
        """Should create nested parent directories."""
        nested_dir = tmp_path / "a" / "b" / "c" / "gtfs"
        zip_path = tmp_path / "test.zip"

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "test content")

        manager = GTFSBundleManager(extract_dir=str(nested_dir))
        manager.extract(zip_path)

        assert nested_dir.exists()
        assert (nested_dir / "test.txt").exists()


class TestGTFSBundleManagerDownloadAndExtract:
    """Tests for GTFSBundleManager.download_and_extract()."""

    @patch.object(GTFSBundleManager, "download")
    @patch.object(GTFSBundleManager, "extract")
    def test_calls_download_and_extract(self, mock_extract, mock_download, tmp_path):
        """Should call download and extract in sequence."""
        zip_path = tmp_path / "test.zip"
        zip_path.touch()
        mock_download.return_value = zip_path
        mock_extract.return_value = tmp_path / "extracted"

        manager = GTFSBundleManager(extract_dir=str(tmp_path / "extracted"))
        manager.download_and_extract()

        mock_download.assert_called_once()
        mock_extract.assert_called_once_with(zip_path)

    @patch.object(GTFSBundleManager, "download")
    @patch.object(GTFSBundleManager, "extract")
    def test_removes_zip_by_default(self, mock_extract, mock_download, tmp_path):
        """Should remove the zip file after extraction by default."""
        zip_path = tmp_path / "test.zip"
        zip_path.touch()
        mock_download.return_value = zip_path

        manager = GTFSBundleManager(extract_dir=str(tmp_path / "extracted"))
        manager.download_and_extract()

        assert not zip_path.exists()

    @patch.object(GTFSBundleManager, "download")
    @patch.object(GTFSBundleManager, "extract")
    def test_keeps_zip_when_requested(self, mock_extract, mock_download, tmp_path):
        """Should keep the zip file when keep_zip=True."""
        zip_path = tmp_path / "test.zip"
        zip_path.write_text("fake zip content")
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        mock_download.return_value = zip_path
        mock_extract.return_value = extract_dir

        manager = GTFSBundleManager(extract_dir=str(extract_dir))
        manager.download_and_extract(keep_zip=True)

        expected_zip = extract_dir / "gtfs.zip"
        assert expected_zip.exists()
        assert not zip_path.exists()

    @patch.object(GTFSBundleManager, "download")
    @patch.object(GTFSBundleManager, "extract")
    def test_returns_extract_dir(self, mock_extract, mock_download, tmp_path):
        """Should return the extraction directory."""
        zip_path = tmp_path / "test.zip"
        zip_path.touch()
        extract_dir = tmp_path / "extracted"
        mock_download.return_value = zip_path
        mock_extract.return_value = extract_dir

        manager = GTFSBundleManager(extract_dir=str(extract_dir))
        result = manager.download_and_extract()

        assert result == extract_dir

    @patch.object(GTFSBundleManager, "download")
    @patch.object(GTFSBundleManager, "extract")
    def test_cleans_up_zip_on_extract_failure(
        self, mock_extract, mock_download, tmp_path
    ):
        """Should remove zip file even if extraction fails."""
        zip_path = tmp_path / "test.zip"
        zip_path.touch()
        mock_download.return_value = zip_path
        mock_extract.side_effect = zipfile.BadZipFile("Corrupt zip")

        manager = GTFSBundleManager(extract_dir=str(tmp_path / "extracted"))

        with pytest.raises(zipfile.BadZipFile):
            manager.download_and_extract()

        assert not zip_path.exists()


class TestGTFSBundleManagerCleanup:
    """Tests for GTFSBundleManager.cleanup()."""

    def test_cleanup_removes_directory(self, temp_extract_dir):
        """Should remove the extraction directory."""
        temp_extract_dir.mkdir(parents=True)
        (temp_extract_dir / "test.txt").write_text("test")

        manager = GTFSBundleManager(extract_dir=str(temp_extract_dir))
        manager.cleanup()

        assert not temp_extract_dir.exists()

    def test_cleanup_handles_nonexistent_directory(self, temp_extract_dir):
        """Should not raise error if directory doesn't exist."""
        manager = GTFSBundleManager(extract_dir=str(temp_extract_dir))
        assert not temp_extract_dir.exists()

        manager.cleanup()  # Should not raise

    def test_cleanup_removes_nested_files(self, temp_extract_dir):
        """Should remove nested directories and files."""
        temp_extract_dir.mkdir(parents=True)
        nested = temp_extract_dir / "subdir" / "nested"
        nested.mkdir(parents=True)
        (nested / "file.txt").write_text("content")

        manager = GTFSBundleManager(extract_dir=str(temp_extract_dir))
        manager.cleanup()

        assert not temp_extract_dir.exists()


class TestGTFSBundleManagerIntegration:
    """Integration tests for GTFSBundleManager."""

    def test_full_extract_workflow(self, sample_gtfs_zip, temp_extract_dir):
        """Test complete workflow with a real zip file."""
        manager = GTFSBundleManager(extract_dir=str(temp_extract_dir))

        # Extract
        result = manager.extract(sample_gtfs_zip)
        assert result == temp_extract_dir
        assert (temp_extract_dir / "stops.txt").exists()

        # Cleanup
        manager.cleanup()
        assert not temp_extract_dir.exists()
