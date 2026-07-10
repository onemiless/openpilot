from openpilot.selfdrive.pandad import pandad


def test_first_start_does_not_reset_a_responsive_panda(mocker):
  reset = mocker.patch.object(pandad.HARDWARE, "reset_internal_panda")
  recover = mocker.patch.object(pandad.HARDWARE, "recover_internal_panda")

  pandad.prepare_internal_panda(0)

  reset.assert_not_called()
  recover.assert_not_called()


def test_recovery_attempts_alternate_reset_and_dfu(mocker):
  reset = mocker.patch.object(pandad.HARDWARE, "reset_internal_panda")
  recover = mocker.patch.object(pandad.HARDWARE, "recover_internal_panda")

  pandad.prepare_internal_panda(1)
  pandad.prepare_internal_panda(2)

  reset.assert_called_once_with()
  recover.assert_called_once_with()


def test_dfu_open_race_is_retried(mocker):
  dfu = mocker.Mock()
  constructor = mocker.patch.object(
    pandad,
    "PandaDFU",
    side_effect=[Exception("transient DFU"), Exception("transient DFU"), dfu],
  )
  mocker.patch.object(pandad.time, "sleep")

  pandad.recover_panda_from_dfu("serial", attempts=3, retry_delay=0.01)

  assert constructor.call_count == 3
  assert all(c.args == ("serial",) for c in constructor.call_args_list)
  dfu.recover.assert_called_once_with()
