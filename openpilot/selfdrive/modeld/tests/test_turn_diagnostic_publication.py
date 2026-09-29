"""Check the model-frame contract of both modelDataV2SP publishers."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[3]
PUBLISHERS = ('selfdrive/modeld/modeld.py', 'sunnypilot/modeld_v2/modeld.py')


def publication_statements(path):
  tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
  for node in ast.walk(tree):
    body = getattr(node, 'body', ())
    if not isinstance(body, list):
      continue
    for index, statement in enumerate(body):
      if (isinstance(statement, ast.Assign) and len(statement.targets) == 1
          and ast.unparse(statement.targets[0]) == 'mdv2sp_send.modelDataV2SP.laneTurnDirection'):
        return compile(ast.Module(body=body[index:index + 3], type_ignores=[]), path, 'exec')
  raise AssertionError(f'{path}: turn diagnostics publisher not found')


def turn_curvature_statements(path):
  tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
  for node in ast.walk(tree):
    body = getattr(node, 'body', ())
    if not isinstance(body, list):
      continue
    for index, statement in enumerate(body):
      if (isinstance(statement, ast.If)
          and ast.unparse(statement.test) == "DH.turn_maneuver.state == 'active'"):
        module = ast.Module(body=body[index:index + 2], type_ignores=[])
        return compile(ast.fix_missing_locations(module), path, 'exec')
  raise AssertionError(f'{path}: active-turn curvature publisher not found')


class _PlanAxes:
  def __init__(self, feature):
    self.feature = feature

  def __getitem__(self, key):
    assert key == (slice(None), 2)
    return f'{self.feature}-z'


class _Plan:
  def __getitem__(self, key):
    rows, feature = key
    assert rows == slice(None)
    return _PlanAxes(feature)


class TurnDiagnosticPublicationTest(unittest.TestCase):
  def test_final_fork_solid_policy_reaches_start_permission_gate(self):
    for path in PUBLISHERS:
      tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
      call = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == 'lane_change_start_permissions'
      )
      keywords = {keyword.arg: ast.unparse(keyword.value) for keyword in call.keywords}
      with self.subTest(path=path):
        self.assertEqual(keywords.get('ignore_solid'), '(left_ignore_solid, right_ignore_solid)')

  def test_active_turn_curvature_helper_is_imported(self):
    for path in PUBLISHERS:
      tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
      imported = {
        alias.asname or alias.name
        for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        for alias in node.names
      }
      with self.subTest(path=path):
        self.assertIn('get_curvature_from_plan', imported)

  def test_frame_validity_and_rejection_reasons(self):
    for path in PUBLISHERS:
      publish = publication_statements(path)
      for model_valid in (False, True):
        for oem_present in (False, True):
          with self.subTest(path=path, model_valid=model_valid, oem_present=oem_present):
            output = SimpleNamespace(laneTurnDirection='none', turnEntryModelMonoTime=0,
                                     turnEntryInputReason='', turnEntryLeftReason='',
                                     turnEntryRightReason='', turnDecisionReason='')
            sp_message = SimpleNamespace(valid=False, modelDataV2SP=output)
            context = {
              'mdv2sp_send': sp_message,
              'modelv2_send': SimpleNamespace(valid=model_valid),
              'meta_main': SimpleNamespace(timestamp_eof=123456789),
              'turn_entry': SimpleNamespace(input_reason='cpModelObserved',
                                            detail_reasons=('boundaryHeld/cpNotTurn', 'openingUnconfirmed/cpNotTurn')),
              'DH': SimpleNamespace(lane_turn_direction='turnRight', turn_decision_reason='turnEntryPending'),
              'oem_gate': object() if oem_present else None,
            }
            exec(publish, context)
            self.assertEqual(sp_message.valid, model_valid)
            self.assertEqual(output.laneTurnDirection, 'turnRight')
            self.assertEqual(output.turnEntryModelMonoTime, 123456789 if oem_present else 0)
            self.assertEqual(output.turnEntryRightReason,
                             'openingUnconfirmed/cpNotTurn' if oem_present else '')
            self.assertEqual(output.turnDecisionReason, 'turnEntryPending' if oem_present else '')

  def test_active_turn_publishes_plan_curvature(self):
    for path in PUBLISHERS:
      publish = turn_curvature_statements(path)
      for state, speed, expected in (('waiting', 8.0, 0.01), ('active', 8.0, 0.125), ('active', 0.0, -0.02)):
        with self.subTest(path=path, state=state, speed=speed):
          action = SimpleNamespace(desiredCurvature=0.01)
          modelv2_action = SimpleNamespace(desiredCurvature=0.01)
          driving_action = SimpleNamespace(desiredCurvature=0.01)
          calls = []

          def get_curvature(yaws, yaw_rates, t_idxs, v_ego, action_t, calls=calls):
            calls.append((yaws, yaw_rates, t_idxs, v_ego, action_t))
            return 0.125

          context = {
            'DH': SimpleNamespace(turn_maneuver=SimpleNamespace(state=state)),
            'Plan': SimpleNamespace(T_FROM_CURRENT_EULER='euler', ORIENTATION_RATE='rate'),
            'ModelConstants': SimpleNamespace(T_IDXS='stock-t'),
            'model': SimpleNamespace(constants=SimpleNamespace(T_IDXS='v2-t'), MIN_LAT_CONTROL_SPEED=0.3,
                                     LAT_SMOOTH_SECONDS=0.0),
            'model_output': {'plan': [_Plan()]},
            'action': action,
            'prev_action': SimpleNamespace(desiredCurvature=-0.02),
            'modelv2_send': SimpleNamespace(modelV2=SimpleNamespace(action=modelv2_action)),
            'drivingdata_send': SimpleNamespace(drivingModelData=SimpleNamespace(action=driving_action)),
            'get_curvature_from_plan': get_curvature,
            'smooth_value': lambda val, prev, tau: val,
            'MIN_LAT_CONTROL_SPEED': 0.3,
            'LAT_SMOOTH_SECONDS': 0.0,
            'v_ego': speed,
            'lat_action_t': 0.2,
          }
          exec(publish, context)

          self.assertEqual(action.desiredCurvature, expected)
          self.assertEqual(modelv2_action.desiredCurvature, expected)
          self.assertEqual(driving_action.desiredCurvature, expected)
          self.assertIs(context['prev_action'], action)
          self.assertEqual(len(calls), int(state == 'active'))
          if calls:
            self.assertEqual(calls[0][:2], ('euler-z', 'rate-z'))
            self.assertEqual(calls[0][2], 'v2-t' if 'modeld_v2' in path else 'stock-t')


if __name__ == '__main__':
  unittest.main()
