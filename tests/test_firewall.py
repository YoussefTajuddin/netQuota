import unittest
from unittest.mock import patch
from netquota.config import Config
from netquota import firewall

class FirewallTests(unittest.TestCase):
 def test_install_generates_ipv4_ipv6_rules(self):
  c=Config('eth0',50000000000,28)
  calls=[]
  def fake_run(*a,**kw):
   calls.append((a,kw));
   class R: returncode=0; stderr=''; stdout=''
   return R()
  with patch('netquota.firewall.subprocess.run',side_effect=fake_run): firewall.install(c,100)
  rules=calls[-1][1]['input']
  self.assertIn('quota internet_quota',rules); self.assertIn('bypass6',rules); self.assertIn('ip6 daddr',rules); self.assertIn('ip daddr != 192.168.0.0/16',rules)
 def test_remaining_never_negative(self):
  c=Config('eth0',100,28); calls=[]
  def fake(*a,**kw): calls.append(kw.get('input','')); return type('R',(),{'returncode':0,'stderr':''})()
  with patch('netquota.firewall.subprocess.run',side_effect=fake): firewall.install(c,999)
  self.assertIn('over 0 bytes',calls[-1])

if __name__=='__main__': unittest.main()
