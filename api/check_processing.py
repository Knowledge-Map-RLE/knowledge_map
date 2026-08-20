"""Check PubMed processing logs and checkpoint."""
from pathlib import Path
import os

# Check for checkpoint file
checkpoint = Path("../data_to_db/logs/parse_checkpoint.txt")
if checkpoint.exists():
    lines = checkpoint.read_text(encoding="utf-8").splitlines()
    print("Checkpoint files: %d" % len(lines))
    if lines:
        print("First 5:", lines[:5])
        print("Last 5:", lines[-5:])
else:
    print("No checkpoint file found at", checkpoint)

# Check for any log files
log_dir = Path("../data_to_db/logs")
if log_dir.exists():
    print("\nLog files:")
    for f in sorted(log_dir.glob("*")):
        print("  %s (%d bytes)" % (f.name, f.stat().st_size))
else:
    print("\nNo log dir at", log_dir)

# Check PubMed data directory
data_dir = Path("../data/PubMed")
if data_dir.exists():
    files = list(data_dir.glob("*.xml.gz"))
    print("\nPubMed XML.gz files: %d" % len(files))
    if files:
        total_size = sum(f.stat().st_size for f in files)
        print("Total size: %.1f GB" % (total_size / (1024**3)))
else:
    print("\nNo PubMed data dir at", data_dir)
