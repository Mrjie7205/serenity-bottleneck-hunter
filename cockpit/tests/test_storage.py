"""Transient Windows locks are retried; persistent denials preserve old data."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
import storage
import triggers
import snapshot


def sharing_error():
    error = PermissionError('fixture sharing violation')
    error.winerror = 32
    return error


class StorageTests(unittest.TestCase):
    def test_transient_alert_replace_retries_then_saves(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'alerts.json';path.write_text('{"old":true}',encoding='utf-8')
            original=triggers.os.replace;calls=[]
            def replace(source,target):
                calls.append(target)
                if len(calls)<3:raise sharing_error()
                return original(source,target)
            with patch.object(triggers.os,'replace',side_effect=replace), patch.object(storage.time,'sleep'):
                triggers._atomic_write(path,{'new':True})
            self.assertEqual(len(calls),3)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')),{'new':True})

    def test_transient_snapshot_replace_retries_then_saves(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'snapshot.json';path.write_text('{"old":true}',encoding='utf-8')
            original=Path.replace;calls=[]
            def replace(source,target):
                calls.append(target)
                if len(calls)==1:raise sharing_error()
                return original(source,target)
            with patch.object(Path,'replace',autospec=True,side_effect=replace), patch.object(storage.time,'sleep'):
                snapshot._write_snapshot(path,{'new':True})
            self.assertEqual(len(calls),2)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')),{'new':True})

    def test_persistent_lock_is_bounded_and_old_file_survives(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'alerts.json';original=b'{"old":true}';path.write_bytes(original)
            with patch.object(triggers.os,'replace',side_effect=sharing_error()) as replace, patch.object(storage.time,'sleep') as sleep:
                with self.assertRaises(triggers._StorageError):triggers._atomic_write(path,{'new':True})
            self.assertEqual(replace.call_count,4)
            self.assertEqual(sleep.call_count,3)
            self.assertEqual(path.read_bytes(),original)
