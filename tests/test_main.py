"""
Unit / integration tests for main.py (FastAPI application).

Run with:
    pip install pytest httpx
    pytest tests/test_main.py -v

No MISTRAL_API_KEY is required for these tests — endpoints that need the key
are tested to verify they return the correct 503 error when the key is absent.
"""

import io
import os

import pytest
from fastapi.testclient import TestClient
from PIL import Image

# Remove any accidental key from the environment before importing the app
os.environ.pop("MISTRAL_API_KEY", None)

from main import app  # noqa: E402

client = TestClient(app)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_payload():
    response = client.get("/health")
    body = response.json()
    assert body["status"] == "healthy"
    assert "service" in body


# ---------------------------------------------------------------------------
# /banks
# ---------------------------------------------------------------------------

def test_banks_returns_200():
    response = client.get("/banks")
    assert response.status_code == 200


def test_banks_returns_dict_of_banks():
    response = client.get("/banks")
    banks = response.json()
    assert isinstance(banks, dict)
    assert len(banks) > 0


def test_banks_each_entry_has_name_and_rib_prefix():
    response = client.get("/banks")
    for _code, info in response.json().items():
        assert "name" in info
        assert "rib_prefix" in info


# ---------------------------------------------------------------------------
# /extract  (Tesseract-based — no API key needed)
# ---------------------------------------------------------------------------

def _make_png_bytes(text_hint: str = "") -> bytes:
    """Return a minimal white PNG image as bytes."""
    buf = io.BytesIO()
    Image.new("RGB", (200, 80), color="white").save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def test_extract_no_file_returns_422():
    response = client.post("/extract")
    assert response.status_code == 422


def test_extract_blank_image_returns_422_or_500():
    """A blank white image produces no OCR text → HTTP 422."""
    png = _make_png_bytes()
    response = client.post(
        "/extract",
        files={"file": ("blank.png", png, "image/png")},
    )
    # Blank image → no extractable text → 422 Unprocessable
    # (or 500 if Tesseract is not installed in the CI environment)
    assert response.status_code in (422, 500)


# ---------------------------------------------------------------------------
# /analyze  (Mistral OCR — requires MISTRAL_API_KEY)
# ---------------------------------------------------------------------------

def test_analyze_without_api_key_returns_503():
    """Without MISTRAL_API_KEY the endpoint must return 503, not 500."""
    os.environ.pop("MISTRAL_API_KEY", None)
    response = client.post(
        "/analyze",
        files={"file": ("doc.png", b"fake-image-data", "image/png")},
    )
    assert response.status_code == 503
    assert "MISTRAL_API_KEY" in response.json()["detail"]


def test_analyze_no_file_returns_422():
    response = client.post("/analyze")
    assert response.status_code == 422
