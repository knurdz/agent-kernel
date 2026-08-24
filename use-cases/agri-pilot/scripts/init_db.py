"""Initialize marketplace SQLite DB."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from marketplace.database import init_db

if __name__ == "__main__":
    init_db()
    print("marketplace DB initialized")
