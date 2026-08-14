class DefaultStoppingPolicy:
  def update_state(self, stopping: bool) -> None:
    del stopping

  def stopping_decel_rate(self, CS, a_target: float, last_output_accel: float) -> float:
    del CS, a_target, last_output_accel
    return 1.0


def create_stopping_policy(backend):
  if backend.control_policy_module is None:
    return DefaultStoppingPolicy()

  from importlib import import_module
  return import_module(backend.control_policy_module).TNStoppingPolicy()
