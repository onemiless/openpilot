import logging

from opendbc.car.carlog import carlog


class ARS408LogAdapter(logging.LoggerAdapter):
  def process(self, msg, kwargs):
    return f"[ARS408:{self.extra['component']}] {msg}", kwargs


def get_ars408_logger(component: str) -> logging.LoggerAdapter:
  """Use the repository car log pipeline while retaining component context."""
  return ARS408LogAdapter(carlog, {"component": component})
