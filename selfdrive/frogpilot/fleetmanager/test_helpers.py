from openpilot.selfdrive.frogpilot.fleetmanager import helpers


def test_set_destination_geocodes_place_name(monkeypatch):
  confirmed = []
  monkeypatch.setattr(helpers, "get_last_lon_lat", lambda: (121.5, 31.2))
  monkeypatch.setattr(helpers, "get_public_token", lambda: "token")
  monkeypatch.setattr(helpers, "search_addr", lambda postvars, lon, lat, valid, token:
                      (postvars["addr_val"], 121.6, 31.3, True, token))
  monkeypatch.setattr(helpers, "nav_confirmed", lambda postvars: confirmed.append(dict(postvars)))

  postvars, valid = helpers.set_destination({"place_name": "test destination"}, False)

  assert valid
  assert postvars["lon"] == 121.6
  assert postvars["lat"] == 31.3
  assert confirmed == [postvars]


def test_set_destination_does_not_confirm_failed_search(monkeypatch):
  confirmed = []
  monkeypatch.setattr(helpers, "get_last_lon_lat", lambda: (121.5, 31.2))
  monkeypatch.setattr(helpers, "get_public_token", lambda: "token")
  monkeypatch.setattr(helpers, "search_addr", lambda postvars, lon, lat, valid, token:
                      (postvars["addr_val"], lon, lat, False, token))
  monkeypatch.setattr(helpers, "nav_confirmed", lambda postvars: confirmed.append(dict(postvars)))

  postvars, valid = helpers.set_destination({"place_name": "missing destination"}, False)

  assert not valid
  assert confirmed == []
  assert "lon" not in postvars
  assert "lat" not in postvars
