"""UWZ gateway agent: runs ON the local gateway (not on Render).

It talks to the cloud with OUTBOUND HTTPS only, keeps working offline, and
queues events in a local SQLite file until they can be synchronized.
Runtime dependency: ``cryptography`` (Ed25519). Everything else is stdlib.
"""
__version__ = '0.1.0'
