import io
import ast
from pathlib import Path
import unittest

from openpilot.system.ui.lib import screen_cast as cast
from openpilot.selfdrive.debug import screen_cast_web as web
from openpilot.system.ui.lib.application import MouseState

ROOT = Path(__file__).resolve().parents[4]

class Params:
  def get_bool(self, key):
    return key in ("C3ScreenCasting", "IsOffroad")


class Tests(unittest.TestCase):
  def test_all_python_syntax(self):
    for name in ('system/ui/lib/screen_cast.py', 'selfdrive/debug/screen_cast_web.py'):
      ast.parse((ROOT/name).read_text(encoding='utf-8'))

  def test_pointer_validation(self):
    self.assertEqual(cast.validate_pointer({'type':'pointer','action':2,'pointerId':1,'x':0.25,'y':1}), (2,1,0.25,1))
    for key,values in {'action':[True,4,'0'],'pointerId':[True,-1,2],'x':[True,float('nan'),float('inf'),-1,2]}.items():
      for value in values:
        p={'type':'pointer','action':0,'pointerId':0,'x':0,'y':1};p[key]=value
        with self.assertRaises(ValueError):cast.validate_pointer(p)

  def test_remote_press_move_release(self):
    m=MouseState()
    for action in (0,2,1):self.assertTrue(m.inject_remote_event(100,50,0,action))
    self.assertEqual([(e.left_pressed,e.left_down,e.left_released) for e in m.get_events()],[(True,True,False),(False,True,False),(False,False,True)])

  def test_rejected_remote_press_cannot_release_local_finger(self):
    m=MouseState();m._local_down[0]=True
    for action in (0,2,1,3):self.assertFalse(m.inject_remote_event(0,0,0,action))
    self.assertEqual(m.get_events(),[])

  def test_local_takeover_does_not_allow_stale_moves_or_releases(self):
    m=MouseState();m.inject_remote_event(0,0,0,0);m.cancel_remote_events()
    m.get_events()
    for action in (2,1,3):self.assertFalse(m.inject_remote_event(0,0,0,action))
    self.assertEqual(m.get_events(),[])

  def test_two_fingers_and_disconnect_release_once(self):
    m=MouseState()
    for slot in (0,1):m.inject_remote_event(10,20,slot,0)
    m.get_events();m.cancel_remote_events();m.cancel_remote_events()
    self.assertEqual([e.slot for e in m.get_events()],[0,1])

  def test_capture_budget_and_high_load_limits(self):
    self.assertEqual(cast.capture_interval(False,20,50,10),0.25)
    self.assertEqual(cast.capture_interval(True,20,50,10),0.5)
    self.assertEqual(cast.capture_interval(True,78,50,10),1)
    self.assertEqual(cast.capture_interval(True,90,50,10),2)
    self.assertEqual(cast.capture_interval(False,20,78,10),2)
    self.assertEqual(cast.capture_interval(False,20,50,80),1)

  def test_disabled_and_no_viewer_never_capture(self):
    r=cast.ScreenCastRuntime(MouseState(),2160,1080,Params())
    r._viewer_active=lambda:False
    self.assertFalse(r.should_capture())
    r._viewer_active=lambda:True;r._enabled=False
    self.assertFalse(r.should_capture())

  def test_capture_queue_bound(self):
    r=cast.ScreenCastRuntime(MouseState(),2160,1080,Params());r._viewer_active=lambda:True
    r._queue.put((1,1,b''));self.assertFalse(r.should_capture())

  def test_websocket_frame_and_handshake(self):
    self.assertEqual(web._accept('dGhlIHNhbXBsZSBub25jZQ=='),'s3pPLMBiTxaQ9kYGzzhZRbK+xOo=')
    payload=b'{"type":"heartbeat"}';mask=b'1234'
    encoded=bytes(v^mask[i%4] for i,v in enumerate(payload))
    self.assertEqual(web._read_frame(io.BytesIO(bytes((0x81,0x80|len(payload)))+mask+encoded)),(1,payload))
    for invalid in [b'\x01\x80',b'\x81\x00',b'\x81\xff',b'\x81\xfe\x20\x00']:
      with self.assertRaises(ValueError):web._read_frame(io.BytesIO(invalid))

  def test_html_has_heartbeat_and_reconnect_state_reset(self):
    page=web.render_page().decode()
    self.assertIn("type:'heartbeat'",page);self.assertIn('pointers.clear()',page)
    self.assertIn('pointercancel',page);self.assertIn('/api/screen/stream',page)

  def test_background_worker_replaces_inherited_cpu0_mask(self):
    from unittest import mock
    scheduler, affinity, priority = mock.Mock(), mock.Mock(), mock.Mock()
    with mock.patch.multiple(cast.os, SCHED_OTHER=0, PRIO_PROCESS=0,
                             sched_setscheduler=scheduler, sched_setaffinity=affinity,
                             sched_param=lambda value: value, setpriority=priority, create=True):
      cast._background_thread(19)
    scheduler.assert_called_once_with(0, 0, 0)
    affinity.assert_called_once_with(0, {0, 1, 2, 3})
    self.assertEqual(priority.call_args.args[-1], 19)

  def test_enabled_state_does_not_poll_params(self):
    r=cast.ScreenCastRuntime(MouseState(),2160,1080,Params())
    r._params.get_bool=lambda key: (_ for _ in ()).throw(AssertionError('unexpected parameter read'))
    for i in range(100):self.assertTrue(r._is_enabled(float(i)))
    r._enabled=False
    self.assertFalse(r.should_capture())

if __name__=='__main__':unittest.main(verbosity=2)
