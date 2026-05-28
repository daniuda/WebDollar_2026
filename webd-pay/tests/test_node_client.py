import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'webd-pay'))

from unittest.mock import patch, Mock
import node_client

def test_get_balance_normal():
    mock_resp = Mock()
    mock_resp.json.return_value = {'balance': 1000000}  # 100 WEBD in sub-units
    mock_resp.raise_for_status = Mock()
    with patch('node_client.requests.get', return_value=mock_resp):
        bal = node_client.get_address_balance('WEBD$test')
    assert bal == 100.0

def test_get_balance_zero():
    mock_resp = Mock()
    mock_resp.json.return_value = {'balance': 0}
    mock_resp.raise_for_status = Mock()
    with patch('node_client.requests.get', return_value=mock_resp):
        bal = node_client.get_address_balance('WEBD$test')
    assert bal == 0.0

def test_get_balance_node_down():
    import requests
    with patch('node_client.requests.get', side_effect=requests.RequestException('down')):
        bal = node_client.get_address_balance('WEBD$test')
    assert bal is None
