import os

# Unit tests run the worker on the host; container behaviour is covered in tests/test_sandbox.py.
os.environ.setdefault("DDG_SANDBOX", "host")
