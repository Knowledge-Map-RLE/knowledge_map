"""Wrapper for opendataloader-pdf-hybrid with __main__ guard.

Without this wrapper, uvicorn.run() on Windows may fail with EADDRINUSE
because the console_scripts entry point lacks `if __name__ == "__main__":`
protection, causing uvicorn's multiprocessing (spawn) to re-import the
module and start a second worker on the same port.
"""
import sys
from opendataloader_pdf.hybrid_server import main

if __name__ == "__main__":
    sys.exit(main())
