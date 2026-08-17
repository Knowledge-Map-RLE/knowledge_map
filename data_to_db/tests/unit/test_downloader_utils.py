"""
Unit tests for downloader_utils and PMC downloader helpers.
"""
import hashlib
import io
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from downloader_utils import (
    md5_of_file,
    parse_ftp_xmlgz_listing,
    parse_md5_file,
    verify_file,
)
from PubMed_Central.pmc_oa_opendata_downloader import PmcOaOpendataDownloader

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_ftp_xmlgz_listing():
    html = (
        '<a href="pubmed25n0001.xml.gz">pubmed25n0001.xml.gz</a> '
        '<a href="pubmed25n0001.xml.gz.md5">md5</a> '
        '<a href="index.html">index</a> '
        '<a href="some.pdf">some.pdf</a>'
    )
    parsed = parse_ftp_xmlgz_listing(html)
    assert list(parsed.keys()) == ["pubmed25n0001.xml.gz"]
    assert parsed["pubmed25n0001.xml.gz"]["md5"] == "pubmed25n0001.xml.gz.md5"


def test_parse_md5_file():
    content = "d41d8cd98f00b204e9800998ecf8427e  pubmed25n0001.xml.gz\n"
    assert parse_md5_file(content) == "d41d8cd98f00b204e9800998ecf8427e"
    assert parse_md5_file("no md5 here") is None


def test_md5_of_file_and_verify():
    tmp = FIXTURES / "tmp_md5_test.bin"
    tmp.write_bytes(b"hello world")
    expected = hashlib.md5(b"hello world").hexdigest()
    try:
        assert md5_of_file(tmp) == expected
        assert verify_file(tmp, expected) is True
        assert verify_file(tmp, "0" * 32) is False
        assert verify_file(Path("nonexistent_file_xyz.bin"), expected) is False
    finally:
        tmp.unlink(missing_ok=True)


def test_verify_file_with_none_md5():
    tmp = FIXTURES / "tmp_md5_none.bin"
    tmp.write_bytes(b"data")
    try:
        assert verify_file(tmp, None) is True
    finally:
        tmp.unlink(missing_ok=True)


def test_extract_image_hrefs():
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <body>
    <p><inline-graphic xlink:href="fig1.jpg"/></p>
    <fig><graphic xlink:href="img/fig2.png"/></fig>
    <media mime-subtype="pdf" xlink:href="article.pdf"/>
    <supplementary-material xlink:href="suppl.xlsx"/>
    <inline-graphic xlink:href="movie.mov"/>
  </body>
</article>
"""
    tmp = FIXTURES / "tmp_image_test.xml"
    tmp.write_bytes(xml)
    try:
        downloader = PmcOaOpendataDownloader()
        hrefs = downloader.extract_image_hrefs(tmp)
        assert hrefs == {"fig1.jpg", "fig2.png"}
    finally:
        tmp.unlink(missing_ok=True)
