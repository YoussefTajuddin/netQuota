import json, tempfile, unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from netquota.duration import seconds
from netquota.vnstat import parse_size
from netquota.state import State
from netquota.config import Config
from netquota.ui import human

class CoreTests(unittest.TestCase):
 def test_duration(self):
  self.assertEqual(seconds('30s'),30); self.assertEqual(seconds('2h'),7200); self.assertEqual(seconds('1d'),86400); self.assertEqual(seconds('1.5h'),5400)
 def test_bad_duration(self):
  for x in ('0h','abc','2x','-1h'):
   with self.assertRaises(ValueError): seconds(x)
 def test_sizes(self):
  self.assertEqual(parse_size('1 KiB'),1024); self.assertEqual(parse_size('1.5 MiB'),1572864); self.assertEqual(parse_size('2 GB'),2000000000)
 def test_bad_size(self):
  with self.assertRaises(ValueError): parse_size('bad')
 def test_state_roundtrip(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'state.json'; s=State.new(28); s.used_bytes=12345; s.blocked=True; s.save(p); t=State.load(p,28); self.assertEqual(t.used_bytes,12345); self.assertTrue(t.blocked)
 def test_atomic_state_json(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'state.json'; State.new(28).save(p);
   with open(p, encoding='utf-8') as f: json.load(f)
 def test_expiry(self):
  now=datetime.now(timezone.utc); s=State(now.isoformat(),(now+timedelta(seconds=1)).isoformat()); self.assertFalse(s.expired(now)); self.assertTrue(s.expired(now+timedelta(seconds=2)))
 def test_config_validation(self):
  c=Config('eth0',50000000000,28); c.validate()
  with self.assertRaises(ValueError): Config('',1,1).validate()
  with self.assertRaises(ValueError): Config('eth0',0,1).validate()
 def test_human(self):
  self.assertEqual(human(1000),'1.00 KB'); self.assertEqual(human(1024,True),'1.00 KiB')
 def test_state_limit_fields(self):
  s=State.new(28); s.used_bytes=-10; self.assertEqual(s.used_bytes,-10)
 def test_duration_whitespace_case(self):
  self.assertEqual(seconds(' 2H '),7200)

if __name__=='__main__': unittest.main()
