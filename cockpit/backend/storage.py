"""Retry brief Windows sharing/access denials without weakening file permissions."""
import time


def replace_with_retry(operation):
    delays = (0.05, 0.10, 0.20)
    for attempt in range(len(delays) + 1):
        try:
            return operation()
        except OSError as error:
            # A reader or antivirus can briefly hold the destination. Permanent
            # denials still fail after a bounded wait; never chmod or discard it.
            if getattr(error, "winerror", None) not in (5, 32, 33) or attempt == len(delays):
                raise
            time.sleep(delays[attempt])
