from types import SimpleNamespace as NS
import ast
from pathlib import Path

import pytest

from openpilot.selfdrive.ui.onroad.alert_localizer import LaneChangePrompt, localize_alert_text


def intent(**updates):
  values = dict(valid=True, signalRequested=True, sessionId='route', routeRevision=1,
                requestId=4, targetLaneIndex=0, direction='left', reason='efficiency:heuristicSignaling')
  return NS(**(values | updates))


def update(prompt, value=None, **updates):
  values = dict(healthy=True, model_healthy=True, model_state='preLaneChange',
                model_direction='left', onroad=True, started_frame=10, language='zh-CHS')
  return prompt.update(value or intent(), **(values | updates))


@pytest.mark.parametrize('direction', ['left', 'right'])
@pytest.mark.parametrize('reason', ['visualNoLeftNeighbor', 'visualNoRightNeighbor',
                                   'radarLeftTargetUnsafe', 'oem399LeftDenied'])
def test_reason_changes_keep_confirmed_overtake_source(direction, reason):
  p = LaneChangePrompt();side = '左' if direction == 'left' else '右'
  assert update(p, intent(direction=direction), model_direction=direction) == f'向{side}超车'
  assert update(p, intent(direction=direction, reason=reason), model_state='laneChangeStarting',
                model_direction=direction) == f'向{side}超车'


@pytest.mark.parametrize('direction', ['left', 'right'])
@pytest.mark.parametrize('source', ['efficiency:heuristicReady', 'heuristicReady'])
def test_withdrawal_keeps_direction_and_names_exit_until_model_leaves(direction, source):
  p = LaneChangePrompt();side = '左' if direction == 'left' else '右'
  kind = '超车' if source.startswith('efficiency:') else '换道'
  update(p, intent(direction=direction, reason=source), model_direction=direction)
  update(p, intent(direction=direction, reason=source), model_direction=direction, model_state='laneChangeStarting')
  withdrawn = intent(signalRequested=False, requestId=0, direction='none', sessionId='', targetLaneIndex=-1,
                     reason='efficiencyCooldown')
  assert update(p, withdrawn, model_state='laneChangeFinishing', model_direction='none') == f'退出{side}{kind}'
  assert update(p, withdrawn, model_state='off', model_direction='none') is None
  assert p.key is None
  assert update(p, intent(requestId=5, reason='heuristicSignaling')) == '向左换道'


def test_model_exit_is_not_labelled_as_continuing_overtake():
  p = LaneChangePrompt();update(p)
  assert update(p, model_state='laneChangeFinishing', model_direction='none') == '退出左超车'


@pytest.mark.parametrize('fault', ['intentHealth', 'modelHealth', 'intentValidity', 'offroad', 'language'])
def test_invalid_context_clears_identity_and_does_not_restore_old_overtake(fault):
  p = LaneChangePrompt();update(p)
  kwargs = {};value = intent()
  if fault == 'intentHealth': kwargs['healthy'] = False
  if fault == 'modelHealth': kwargs['model_healthy'] = False
  if fault == 'intentValidity': value.valid = False
  if fault == 'offroad': kwargs['onroad'] = False
  if fault == 'language': kwargs['language'] = 'en'
  assert update(p, value, **kwargs) is None
  assert p.key is None
  assert update(p, intent(requestId=5, reason='heuristicReady')) == '向左换道'


@pytest.mark.parametrize('field,value', [('sessionId', 'new'), ('routeRevision', 2), ('requestId', 5), ('direction', 'right')])
def test_new_request_or_route_does_not_inherit_source(field, value):
  p = LaneChangePrompt();update(p)
  current = intent(reason='heuristicSignaling', **{field: value})
  assert update(p, current, model_direction=str(current.direction)) == ('向右换道' if field == 'direction' else '向左换道')


def test_new_request_during_old_execution_waits_for_model_to_settle():
  p = LaneChangePrompt();update(p, model_state='laneChangeStarting')
  new = intent(requestId=5, reason='heuristicSignaling')
  assert update(p, new, model_state='laneChangeFinishing') is None
  assert update(p, new, model_state='laneChangeFinishing') is None
  assert update(p, new, model_state='preLaneChange') == '向左换道'


@pytest.mark.parametrize('field,value', [('sessionId', 'new'), ('routeRevision', 2)])
def test_route_change_during_execution_cannot_attach_to_the_old_model_tail(field, value):
  p = LaneChangePrompt();update(p, model_state='laneChangeStarting')
  new = intent(reason='heuristicSignaling', **{field: value})
  assert update(p, new, model_state='laneChangeFinishing', model_direction='none') is None
  assert update(p, new, model_state='laneChangeFinishing', model_direction='none') is None
  assert update(p, new, model_state='off', model_direction='none') == '向左换道'


def test_model_direction_conflict_does_not_display_opposite_side():
  p = LaneChangePrompt();update(p)
  assert update(p, model_state='laneChangeStarting', model_direction='right') is None
  assert p.key is None


def test_new_onroad_epoch_does_not_reuse_same_request_identity():
  p = LaneChangePrompt();update(p)
  assert update(p, intent(reason='heuristicReady'), started_frame=100) == '向左换道'


def test_manual_signal_and_unknown_request_do_not_create_automatic_source():
  p = LaneChangePrompt()
  assert update(p, intent(signalRequested=False), model_state='laneChangeStarting') is None
  assert update(p, intent(requestId=0), model_state='laneChangeStarting') is None


def test_turn_keeps_existing_text_and_clears_lane_change_identity():
  p = LaneChangePrompt();update(p)
  assert update(p, intent(targetLaneIndex=-1, direction='right', reason='turnApproach')) == '正在右转'
  assert p.key is None


def renderer():
  # Execute the real render decision with no window, sockets or GPU dependency.
  path = Path(__file__).resolve().parents[1] / 'onroad/alert_renderer.py'
  tree = ast.parse(path.read_text(encoding='utf-8'))
  cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'AlertRenderer')
  fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'get_alert')
  code = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), fn], type_ignores=[])
  env = dict(ui_state=NS(started=True, started_frame=10), multilang=NS(language='zh-CHS'),
             localize_alert_text=localize_alert_text, Alert=NS)
  exec(compile(ast.fix_missing_locations(code), str(path), 'exec'), env)
  class SM(dict):
    updated = {'selfdriveState': True}
    recv_frame = {k:20 for k in ('selfdriveState', 'modelV2', 'navLaneIntentSP')}
    seen = alive = valid = {k:True for k in ('modelV2', 'navLaneIntentSP')}
  sm = SM(selfdriveState=NS(alertSize=0, alertText1='', alertText2='', alertType='', alertStatus=NS(raw=0)),
          modelV2=NS(meta=NS(laneChangeState='preLaneChange', laneChangeDirection='left')),
          navLaneIntentSP=intent())
  return env['get_alert'], NS(_lane_change_prompt=LaneChangePrompt()), sm


def test_renderer_observes_source_before_changing_lanes_alert_is_visible():
  get_alert, widget, sm = renderer()
  assert get_alert(widget, sm) is None
  sm['navLaneIntentSP'].reason = 'visualNoLeftNeighbor'
  sm['modelV2'].meta.laneChangeState = 'laneChangeStarting'
  sm['selfdriveState'].alertSize = NS(raw=1)
  sm['selfdriveState'].alertText1 = 'Changing Lanes'
  assert get_alert(widget, sm).text1 == '向左超车'


def test_renderer_keeps_other_alert_priority_while_tracking_source():
  get_alert, widget, sm = renderer()
  sm['selfdriveState'].alertSize = NS(raw=1)
  sm['selfdriveState'].alertText1 = 'BRAKE!'
  assert get_alert(widget, sm).text1 == '刹车！'
  sm['modelV2'].meta.laneChangeState = 'laneChangeStarting'
  sm['navLaneIntentSP'].reason = 'oem399LeftDenied'
  sm['selfdriveState'].alertText1 = 'Changing Lanes'
  assert get_alert(widget, sm).text1 == '向左超车'


def test_renderer_does_not_observe_old_onroad_messages_as_new_source():
  get_alert, widget, sm = renderer()
  sm.recv_frame = {k:5 for k in ('selfdriveState', 'modelV2', 'navLaneIntentSP')}
  assert get_alert(widget, sm) is None
  assert widget._lane_change_prompt.key is None
