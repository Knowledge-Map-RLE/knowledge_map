"""
Unit tests for bibliographic reference extraction from PubMed Central XML files
"""
import sys
from pathlib import Path
from lxml import etree as LET

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from PubMed_Central.pmc_oa_bulk_to_db import extract_bibliographic_links_optimized


def test_extract_references_from_sample_xml():
    """Test that we correctly extract all 5 references from sample XML"""

    # Load sample XML
    xml_path = Path(__file__).parent / "fixtures" / "sample_pmc_article.xml"
    with open(xml_path, 'rb') as f:
        tree = LET.parse(f)
        root = tree.getroot()

    # Extract references
    primary_id = "12345678"
    links = extract_bibliographic_links_optimized(root, primary_id)

    # Should extract exactly 5 references
    assert len(links) == 5, f"Expected 5 references, but got {len(links)}"

    # Verify each reference has required data
    for i, link in enumerate(links, 1):
        assert any(link.get(key) for key in ['pmid', 'pmcid', 'doi', 'url', 'title']), \
            f"Reference {i} missing all identifiers and title"

    print(f"[PASS] Test passed: Extracted {len(links)} references from sample XML")
    return links


def test_reference_identifiers():
    """Test that we correctly extract different types of identifiers"""

    xml_path = Path(__file__).parent / "fixtures" / "sample_pmc_article.xml"
    with open(xml_path, 'rb') as f:
        tree = LET.parse(f)
        root = tree.getroot()

    primary_id = "12345678"
    links = extract_bibliographic_links_optimized(root, primary_id)

    # Check specific references have correct identifiers
    pmids = [link.get('pmid') for link in links if link.get('pmid')]
    pmcids = [link.get('pmcid') for link in links if link.get('pmcid')]
    dois = [link.get('doi') for link in links if link.get('doi')]
    urls = [link.get('url') for link in links if link.get('url')]

    assert '11111111' in pmids, "Should extract PMID from ref1"
    assert 'PMC2222222' in pmcids or '2222222' in pmcids, "Should extract PMCID from ref2"
    assert any('10.5555/test.2022.003' in doi for doi in dois), "Should extract DOI from ref3"
    assert any('https://example.com/article/4' in url for url in urls), "Should extract URL from ref4"

    print("[PASS] Test passed: All identifier types extracted correctly")
    print(f"  - PMIDs: {len(pmids)}")
    print(f"  - PMCIDs: {len(pmcids)}")
    print(f"  - DOIs: {len(dois)}")
    print(f"  - URLs: {len(urls)}")


def test_reference_deduplication():
    """Test that duplicate references are removed"""

    # Create XML with duplicate references
    xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
<article>
  <front>
    <article-meta>
      <article-id pub-id-type="pmid">99999999</article-id>
    </article-meta>
  </front>
  <back>
    <ref-list>
      <ref id="ref1">
        <element-citation>
          <article-title>Duplicate article</article-title>
          <pub-id pub-id-type="pmid">88888888</pub-id>
        </element-citation>
      </ref>
      <ref id="ref2">
        <element-citation>
          <article-title>Duplicate article</article-title>
          <pub-id pub-id-type="pmid">88888888</pub-id>
        </element-citation>
      </ref>
      <ref id="ref3">
        <element-citation>
          <article-title>Different article</article-title>
          <pub-id pub-id-type="pmid">77777777</pub-id>
        </element-citation>
      </ref>
    </ref-list>
  </back>
</article>
"""

    root = LET.fromstring(xml_content)
    primary_id = "99999999"
    links = extract_bibliographic_links_optimized(root, primary_id)

    # Should only have 2 unique references (duplicate removed)
    assert len(links) == 2, f"Expected 2 unique references after deduplication, but got {len(links)}"

    print("[PASS] Test passed: Duplicate references removed correctly")


def test_reference_titles_extracted():
    """Test that reference titles are extracted when available"""

    xml_path = Path(__file__).parent / "fixtures" / "sample_pmc_article.xml"
    with open(xml_path, 'rb') as f:
        tree = LET.parse(f)
        root = tree.getroot()

    primary_id = "12345678"
    links = extract_bibliographic_links_optimized(root, primary_id)

    # Count how many references have titles
    refs_with_titles = [link for link in links if link.get('title')]

    assert len(refs_with_titles) >= 4, f"Expected at least 4 references with titles, got {len(refs_with_titles)}"

    print(f"[PASS] Test passed: {len(refs_with_titles)}/{len(links)} references have titles extracted")


def test_empty_reference_list():
    """Test handling of articles without references"""

    xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
<article>
  <front>
    <article-meta>
      <article-id pub-id-type="pmid">00000000</article-id>
      <title-group>
        <article-title>Article without references</article-title>
      </title-group>
    </article-meta>
  </front>
  <body>
    <p>No references section</p>
  </body>
</article>
"""

    root = LET.fromstring(xml_content)
    primary_id = "00000000"
    links = extract_bibliographic_links_optimized(root, primary_id)

    # Should return empty list, not crash
    assert len(links) == 0, f"Expected 0 references for article without ref-list, got {len(links)}"

    print("[PASS] Test passed: Empty reference list handled correctly")


def run_all_tests():
    """Run all tests and report results"""
    print("\n" + "="*60)
    print("Running Reference Extraction Tests")
    print("="*60 + "\n")

    tests = [
        ("Extract all references", test_extract_references_from_sample_xml),
        ("Extract identifier types", test_reference_identifiers),
        ("Deduplicate references", test_reference_deduplication),
        ("Extract titles", test_reference_titles_extracted),
        ("Handle empty ref-list", test_empty_reference_list),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            print(f"\n[TEST] {test_name}")
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] Test failed: {e}")
            failed += 1
        except Exception as e:
            print(f"[ERROR] Test error: {e}")
            failed += 1

    print("\n" + "="*60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("="*60 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
