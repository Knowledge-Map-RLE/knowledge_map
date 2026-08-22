import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from PubMed_Central.pmc_oa_bulk_to_db import process_all_local_articles

if __name__ == "__main__":
    print("Starting PMC article processing...")
    process_all_local_articles()
    print("Processing complete.")
