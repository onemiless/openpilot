#!/usr/bin/env python3
"""Render actual mici widgets and serialized traffic inputs; save PNG evidence."""
import json, os, time, uuid
from pathlib import Path
os.environ['OPENPILOT_PREFIX']='sp-ui-'+uuid.uuid4().hex[:10]
from openpilot.common.prefix import OpenpilotPrefix
prefix = OpenpilotPrefix(prefix=os.environ['OPENPILOT_PREFIX'])
prefix.__enter__()
os.environ['BIG']='0'
os.environ['SCALE']='1'
import pyray as rl
from openpilot.cereal import messaging
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import multilang
from openpilot.selfdrive.ui.sunnypilot.onroad.traffic_control import TrafficControlRenderer, traffic_card_rect
from openpilot.selfdrive.ui.sunnypilot.mici.layouts.tesla import TeslaSettingsMici
from openpilot.system.ui.widgets.scroller import NavScroller

out=Path('artifacts/sp-tesla-migration/ui');out.mkdir(parents=True,exist_ok=True)
ui_state.params.put('LanguageSetting','zh-CHS',block=True)
ui_state.params.put_bool('IsOffroad',True,block=True)
ui_state.started=False
renderer=TrafficControlRenderer(compact=True)
pm=messaging.PubMaster(['longitudinalPlanSP'])
multilang.change_language('zh-CHS')
gui_app.init_window('Tesla migration mici E2E',fps=30)
assert (gui_app.width,gui_app.height)==(536,240)
rect=rl.Rectangle(0,0,536,240);card=traffic_card_rect(rect,compact=True)
assert 0<=card.x and 0<=card.y and card.x+card.width<=536 and card.y+card.height<=240
results=[]
for index,_ in enumerate(gui_app.render()):
  case=min(index//20,2)
  msg=messaging.new_message('longitudinalPlanSP');msg.valid=case!=2
  traffic=msg.longitudinalPlanSP.teslaTrafficControl
  traffic.mode=4;traffic.phase=2;traffic.rawDistance=25;traffic.quality=2
  traffic.lightState=1 if case==0 else 2
  pm.send('longitudinalPlanSP',msg);ui_state.sm.update(10);renderer.update()
  renderer.render(rect)
  if index in (18,38,58):
    name=['traffic-red','traffic-green','traffic-invalid'][case]
    rl.rl_draw_render_batch_active()
    rl.take_screenshot(str(out/(name+'.png')))
    assert renderer.state.visible == (case != 2)
    assert renderer.state.light_state == ([1,2,0][case])
    results.append({'case':name,'visible':renderer.state.visible,'signal':renderer.state.light_state})
  if index==60:
    root=NavScroller();gui_app.push_widget(root)
    settings=TeslaSettingsMici();gui_app.push_widget(settings)
    assert gui_app._nav_stack[-1] is settings
  if index==70:
    rl.rl_draw_render_batch_active()
    rl.take_screenshot(str(out/'tesla-settings.png'))
    settings._choose_param('TeslaBlindspotAmbientBrightness',[('30%',30),('91%',91)])
    assert len(gui_app._nav_stack)==3
  if index==78:
    child=gui_app._nav_stack[-1]
    child._scroller._items[2]._click_callback()
    assert ui_state.params.get('TeslaBlindspotAmbientBrightness')==91
    assert gui_app._nav_stack[-1] is settings
    results.append({'case':'settings-select-return','night_brightness':91,'returned':True})
  if index==82:
    settings._scroller.scroll_to(422, smooth=False)
  if index==86:
    target=settings._scroller._items[1].rect
    assert target.x < 536 and target.x + target.width > 0
    rl.rl_draw_render_batch_active()
    rl.take_screenshot(str(out/'cooperative-steering.png'))
    settings._tuning_page(__import__('openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.registry',fromlist=['ordered_backends']).ordered_backends()[2])
    gui_app._nav_stack[-1]._scroller.scroll_to(1688,smooth=False)
  if index==94:
    rl.rl_draw_render_batch_active()
    rl.take_screenshot(str(out/'tn-tuning.png'))
    gui_app.pop_widget()
  if index==100:
    settings._scroller._items[0]._click_callback()
    assert gui_app._nav_stack[-1] is root
    results.append({'case':'settings-back','returned':True})
    gui_app.request_close()
(out/'summary.json').write_text(json.dumps({'viewport':[536,240],'cases':results,'scope':'native rendering/navigation callbacks and serialized traffic messages; no physical C4'},indent=2)+'\n')
gui_app.close()
prefix.__exit__(None,None,None)
