"""Makes the `skb` package importable when pytest is run from any folder.

pytest puts the folder holding this file on sys.path, so
`python -m pytest -q` works both here and from the parent directory.
"""
