import unittest
from unittest.mock import patch
from netquota import network

class NetworkTests(unittest.TestCase):
 def test_default_interface(self):
  data='[{"dev":"eth0"}]'
  with patch('netquota.network.run') as r: r.return_value.stdout=data; self.assertEqual(network.default_interface(),'eth0')
 def test_addresses(self):
  data='[{"addr_info":[{"family":"inet","local":"192.168.1.2"},{"family":"inet6","local":"2001:db8::1"}]}]'
  with patch('netquota.network.run') as r: r.return_value.stdout=data; self.assertEqual(network.interface_addresses('eth0'),(['192.168.1.2'],['2001:db8::1']))
 def test_interface_filters_virtual(self):
  data='[{"ifname":"lo","flags":["UP"]},{"ifname":"eth0","flags":["UP"]},{"ifname":"docker0","flags":["UP"]},{"ifname":"wlp0s0","flags":[]}]'
  with patch('netquota.network.run') as r: r.return_value.stdout=data; names=[x['name'] for x in network.interfaces()]; self.assertEqual(names,['eth0','wlp0s0'])

if __name__=='__main__': unittest.main()
