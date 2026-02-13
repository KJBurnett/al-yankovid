import json


def test_send_message_direct_recipient_builds_payload(fake_process):
    import signal_manager
    p = fake_process
    signal_manager.send_message(p, None, '+123', 'hello', attachments=['/tmp/a.mp4'])
    val = p.stdin.getvalue().strip()
    payload = json.loads(val)
    assert payload['method'] == 'send'
    assert payload['params']['message'] == 'hello'
    assert payload['params']['recipient'] == '+123'
    assert payload['params']['attachments'] == ['/tmp/a.mp4']


def test_send_message_group_recipient(fake_process):
    import signal_manager
    p = fake_process
    signal_manager.send_message(p, 'group-id', None, 'hi', attachments=None)
    val = p.stdin.getvalue().strip()
    payload = json.loads(val)
    assert payload['params']['groupId'] == 'group-id'
    assert 'recipient' not in payload['params']
