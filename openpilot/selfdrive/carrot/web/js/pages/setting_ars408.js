"use strict";

(function () {
  const GROUP = "VEH_RADAR";
  const CARD_ID = "ars408ControlCard";
  const POLL_MS = 1000;
  const FILTER_NAMES = [
    "Object count", "Distance", "Azimuth", "Approaching relative speed", "Departing relative speed",
    "RCS", "Lifetime", "Size", "Probability", "Lateral Y", "Longitudinal X",
    "Lateral left-to-right speed", "Longitudinal approaching speed",
    "Lateral right-to-left speed", "Longitudinal departing speed",
  ];
  const FILTER_BOUNDS = [
    [0, 100], [0, 409.5], [-50, 52.375], [0, 128.9925], [0, 128.9925],
    [-50, 52.375], [0, 409.5], [0, 102.375], [0, 7], [-409.5, 409.5],
    [-500, 1138.2], [0, 128.9925], [0, 128.9925], [0, 128.9925], [0, 128.9925],
  ];
  const COPY = {
    title: { ko: "Tesla ARS408 레이더 제어", en: "Tesla ARS408 Radar Control", zh: "Tesla ARS408 雷达控制" },
    subtitle: { ko: "실제 0x201/0x204 회신 기준", en: "Based on live 0x201/0x204 replies", zh: "以实时 0x201/0x204 回读为准" },
    online: { ko: "온라인", en: "Online", zh: "在线" },
    offline: { ko: "오프라인", en: "Offline", zh: "离线" },
    refresh: { ko: "새로 고침", en: "Refresh", zh: "刷新" },
    distance: { ko: "최대 거리", en: "Max distance", zh: "最大距离" },
    extended: { ko: "확장 정보", en: "Extended info", zh: "扩展信息" },
    output: { ko: "출력 유형", en: "Output type", zh: "输出类型" },
    quality: { ko: "품질 정보", en: "Quality", zh: "质量信息" },
    motion: { ko: "운동 입력 상태", en: "MotionRx", zh: "运动输入状态" },
    sensor: { ko: "센서 ID", en: "Sensor ID", zh: "传感器 ID" },
    filterState: { ko: "필터 상태", en: "Filter state", zh: "过滤器状态" },
    configResult: { ko: "설정 결과", en: "Config result", zh: "配置结果" },
    filterResult: { ko: "필터 결과", en: "Filter result", zh: "过滤结果" },
    on: { ko: "켜짐", en: "On", zh: "开启" },
    off: { ko: "꺼짐", en: "Off", zh: "关闭" },
    objects: { ko: "Objects", en: "Objects", zh: "Objects" },
    objectLimit: { ko: "목표 수 상한", en: "Object limit", zh: "目标数量上限" },
    readFilter: { ko: "필터 읽기", en: "Read filter", zh: "读取过滤器" },
    writeFilter: { ko: "고급 필터 설정", en: "Advanced filter", zh: "高级过滤器" },
    ram: { ko: "현재만 적용", en: "Apply to RAM", zh: "仅当前生效" },
    nvm: { ko: "NVM 저장", en: "Save to NVM", zh: "写入 NVM" },
    disabled: { ko: "먼저 ARS408 모드를 켜고 재시작하세요.", en: "Enable ARS408 mode and restart first.", zh: "请先启用 ARS408 模式并重启。" },
    restartPending: { ko: "선택한 모드는 재시작 후 적용됩니다.", en: "The selected mode will apply after restart.", zh: "所选模式将在重启后生效。" },
    radarOffline: { ko: "ARS408 RadarState를 기다리는 중입니다.", en: "Waiting for ARS408 RadarState.", zh: "正在等待 ARS408 RadarState。" },
    applyInactive: { ko: "점화를 켜고 ARS408 제어 루프가 시작될 때까지 기다리세요.", en: "Turn ignition on and wait for the ARS408 apply loop.", zh: "请打开点火并等待 ARS408 控制循环启动。" },
    stationaryRequired: { ko: "차량을 정지하고 openpilot을 해제해야 설정할 수 있습니다.", en: "Stop the vehicle and disengage openpilot before configuring.", zh: "配置前请停车并退出 openpilot 接管。" },
    prerequisitesFailed: { ko: "필수 조건 불일치: bus 1, Sensor ID 0, Objects Quality 1을 확인하세요.", en: "Prerequisite mismatch: verify bus 1, Sensor ID 0, and Objects Quality 1.", zh: "前提不匹配：请确认 bus 1、Sensor ID 0，以及 Objects 模式下 Quality 1。" },
    danger: { ko: "레이더 출력이 즉시 바뀔 수 있습니다. 운전자가 주행 중 조작하지 마세요.", en: "Radar output may change immediately. The driver must not operate this while driving.", zh: "雷达输出可能立即变化，驾驶员不得在行驶中操作。" },
  };
  const state = { timer: null, loading: false, payload: null };

  function language() {
    const value = String(document.documentElement.lang || globalThis.LANG || "en").toLowerCase();
    if (value.startsWith("ko")) return "ko";
    if (value.startsWith("zh")) return "zh";
    return "en";
  }

  function text(key) {
    const entry = COPY[key];
    return entry?.[language()] || entry?.en || key;
  }

  function groupVisible() {
    const box = document.getElementById("items");
    return Boolean(box && box.dataset.renderedGroup === GROUP && !box.dataset.renderedDetail);
  }

  function visible() {
    return groupVisible() && state.payload?.supported !== false;
  }

  function makeButton(label, action, tone = "", actionKind = "write") {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `smallBtn ars408-action${tone ? ` btn--${tone}` : ""}`;
    button.textContent = label;
    button.dataset.ars408ActionKind = actionKind;
    button.addEventListener("click", action);
    return button;
  }

  function metric(label, role) {
    const item = document.createElement("div");
    item.className = "ars408-metric";
    const key = document.createElement("small");
    key.textContent = label;
    const value = document.createElement("b");
    value.dataset.role = role;
    value.textContent = "-";
    item.append(key, value);
    return item;
  }

  function ensureCard() {
    if (!visible()) return null;
    const box = document.getElementById("items");
    let card = document.getElementById(CARD_ID);
    if (card) return card;
    card = document.createElement("section");
    card.id = CARD_ID;
    card.className = "setting-group-card ars408-card";

    const heading = document.createElement("div");
    heading.className = "ars408-heading";
    const copy = document.createElement("div");
    const title = document.createElement("div");
    title.className = "ars408-title";
    title.textContent = text("title");
    const subtitle = document.createElement("div");
    subtitle.className = "muted";
    subtitle.textContent = text("subtitle");
    copy.append(title, subtitle);
    const badge = document.createElement("span");
    badge.className = "ars408-status";
    badge.dataset.role = "online";
    badge.textContent = text("offline");
    heading.append(copy, badge);

    const metrics = document.createElement("div");
    metrics.className = "ars408-metrics";
    metrics.append(
      metric(text("distance"), "distance"), metric(text("output"), "output"),
      metric(text("extended"), "extended"), metric(text("quality"), "quality"),
      metric(text("motion"), "motion"), metric(text("sensor"), "sensor"),
    );

    const fixed = document.createElement("div");
    fixed.className = "ars408-fixed muted";
    fixed.dataset.role = "fixed";
    const filter = document.createElement("div");
    filter.className = "ars408-result";
    filter.dataset.role = "filter";
    const result = document.createElement("div");
    result.className = "ars408-result";
    result.dataset.role = "result";
    const hint = document.createElement("div");
    hint.className = "ars408-hint";
    hint.dataset.role = "hint";

    const actions = document.createElement("div");
    actions.className = "ui-action-grid ui-action-grid--quick ars408-actions";
    actions.append(
      makeButton(text("refresh"), refresh, "", "refresh"),
      makeButton(text("distance"), () => configureField("max_distance", Array.from({ length: 26 }, (_, i) => 200 + i * 2))),
      makeButton(text("extended"), () => configureField("send_extended", [0, 1])),
      makeButton(text("output"), () => configureField("output_type", [0, 1])),
      makeButton(text("objectLimit"), configureObjectLimit),
      makeButton(text("readFilter"), queryFilter, "", "read"),
      makeButton(text("writeFilter"), configureFilter, "warning"),
    );

    card.append(heading, metrics, fixed, filter, result, hint, actions);
    box.insertBefore(card, box.firstChild);
    return card;
  }

  function setRole(card, role, value) {
    const node = card?.querySelector(`[data-role="${role}"]`);
    if (node) node.textContent = value == null || value === "" ? "-" : String(value);
  }

  function displayValue(value) {
    return value === null || value === undefined || value === "" ? "-" : String(value);
  }

  function setTeslaRowsVisible(show) {
    for (const name of ["TeslaRadarMode", "TeslaRadarMotionInput"]) {
      const row = document.querySelector(`.setting[data-setting-name="${name}"]`);
      if (row) row.hidden = !show;
    }
  }

  function render() {
    const payload = state.payload;
    if (!payload) return;
    if (payload.supported === false) {
      setTeslaRowsVisible(false);
      document.getElementById(CARD_ID)?.remove();
      return;
    }
    setTeslaRowsVisible(true);
    const card = ensureCard();
    if (!card) return;
    const online = card.querySelector('[data-role="online"]');
    online.textContent = payload.online ? text("online") : text("offline");
    online.classList.toggle("is-online", Boolean(payload.online));
    setRole(card, "distance", payload.state?.maxDistance ? `${payload.state.maxDistance} m` : "-");
    setRole(card, "output", payload.state?.outputType === "1" ? text("objects") : payload.state?.outputType === "0" ? text("off") : payload.state?.outputType);
    setRole(card, "extended", payload.state?.extended);
    setRole(card, "quality", payload.state?.quality);
    setRole(card, "motion", payload.state?.motionRx);
    setRole(card, "sensor", payload.state?.sensorId);
    setRole(card, "fixed", `Relay ${displayValue(payload.state?.ctrlRelay)} · RCS ${displayValue(payload.state?.rcsThreshold)} · Power ${displayValue(payload.state?.power)} · Sort ${displayValue(payload.state?.sort)} · NVM R/W ${displayValue(payload.state?.nvmRead)}/${displayValue(payload.state?.nvmWrite)}`);
    setRole(card, "filter", `${text("filterState")}: ${payload.filterState || "-"}`);
    setRole(card, "result", `${text("configResult")}: ${payload.configResult || "-"} · ${text("filterResult")}: ${payload.filterResult || "-"}`);
    const desiredMode = Number(payload.desiredMode || 0);
    const activeMode = Number(payload.activeMode || 0);
    const ready = Boolean(payload.controllerReady) && activeMode > 0;
    const prerequisitesOk = payload.prerequisites?.sensorIdOk !== false && payload.prerequisites?.qualityOk !== false;
    const readable = ready && Boolean(payload.online) && desiredMode === activeMode && Boolean(payload.applyReady);
    const writable = readable && Boolean(payload.vehicleStandstill) && !payload.controlsEnabled && prerequisitesOk;
    const hint = desiredMode !== activeMode
      ? text("restartPending")
      : !ready
        ? text("disabled")
        : !payload.online
          ? text("radarOffline")
          : !payload.applyReady
            ? text("applyInactive")
          : !prerequisitesOk
            ? text("prerequisitesFailed")
          : !payload.vehicleStandstill || payload.controlsEnabled
            ? text("stationaryRequired")
          : text("danger");
    setRole(card, "hint", hint);
    card.querySelectorAll(".ars408-action").forEach((button) => {
      const kind = button.dataset.ars408ActionKind;
      if (kind === "refresh") return;
      button.disabled = kind === "read" ? !readable : !writable;
    });
  }

  async function refresh() {
    if (!groupVisible() || state.loading) return;
    state.loading = true;
    try {
      state.payload = await getJson("/api/ars408");
      render();
    } catch (error) {
      showAppToast(error?.message || "ARS408 status failed", { tone: "error" });
    } finally {
      state.loading = false;
    }
  }

  async function choose(title, values, label = (value) => String(value)) {
    return openAppDialog({
      mode: "choice", choiceLayout: "value-grid", title,
      choices: values.map((value) => ({ label: label(value), value: String(value) })),
      cancelLabel: typeof getUIText === "function" ? getUIText("cancel", "Cancel") : "Cancel",
      showCancel: true,
    });
  }

  async function confirmDanger(action) {
    return appConfirm(`${action}\n\n${text("danger")}`, {
      title: text("title"),
      confirmLabel: typeof getUIText === "function" ? getUIText("ok", "OK") : "OK",
      cancelLabel: typeof getUIText === "function" ? getUIText("cancel", "Cancel") : "Cancel",
    });
  }

  async function post(path, body) {
    try {
      const result = await postJson(path, body);
      showAppToast(`ARS408 request ${result.requestId}`);
      window.setTimeout(refresh, 250);
    } catch (error) {
      showAppToast(error?.message || "ARS408 request failed", { tone: "error" });
    }
  }

  async function configureField(field, values) {
    const selected = await choose(text(field === "max_distance" ? "distance" : field === "send_extended" ? "extended" : "output"), values,
      (value) => field === "max_distance" ? `${value} m` : field === "output_type" ? (value ? text("objects") : text("off")) : (value ? text("on") : text("off")));
    if (selected === null) return;
    const storeChoice = await choose(text("title"), [0, 1], (value) => value ? text("nvm") : text("ram"));
    if (storeChoice === null) return;
    if (!await confirmDanger(`${field}: ${selected}`)) return;
    await post("/api/ars408/config", { field, value: Number(selected), store: storeChoice === "1", confirm: true });
  }

  async function configureObjectLimit() {
    const selected = await choose(text("objectLimit"), [32, 48, 64], (value) => String(value));
    if (selected === null || !await confirmDanger(`${text("objectLimit")}: ${selected}`)) return;
    await post("/api/ars408/filter", { index: 0, active: 1, minimum: 0, maximum: Number(selected), confirm: true });
  }

  async function queryFilter() {
    const selected = await choose(text("readFilter"), FILTER_NAMES.map((_, index) => index),
      (index) => `${index}: ${FILTER_NAMES[index]}`);
    if (selected === null) return;
    await post("/api/ars408/filter", { action: "query", index: Number(selected) });
  }

  async function configureFilter() {
    const selected = await choose(text("writeFilter"), FILTER_NAMES.map((_, index) => index),
      (index) => `${index}: ${FILTER_NAMES[index]}`);
    if (selected === null) return;
    const index = Number(selected);
    const activeChoice = await choose(text("writeFilter"), [0, 1], (value) => value ? text("on") : text("off"));
    if (activeChoice === null) return;
    const bounds = FILTER_BOUNDS[index];
    const minimumRaw = index === 0 ? "0" : await appPrompt(`${FILTER_NAMES[index]} min ${bounds[0]}..${bounds[1]}`, { defaultValue: String(bounds[0]), showCancel: true });
    if (minimumRaw === null) return;
    const maximumRaw = await appPrompt(`${FILTER_NAMES[index]} max ${bounds[0]}..${bounds[1]}`, { defaultValue: String(bounds[1]), showCancel: true });
    if (maximumRaw === null) return;
    const minimum = Number(minimumRaw);
    const maximum = Number(maximumRaw);
    if (!Number.isFinite(minimum) || !Number.isFinite(maximum) || minimum < bounds[0] || maximum > bounds[1] || minimum > maximum) {
      showAppToast("Invalid ARS408 filter range", { tone: "error" });
      return;
    }
    if (!await confirmDanger(`${index}: ${minimum}..${maximum}`)) return;
    await post("/api/ars408/filter", { index, active: Number(activeChoice), minimum, maximum, confirm: true });
  }

  function sync() {
    if (!groupVisible()) {
      if (state.timer) window.clearInterval(state.timer);
      state.timer = null;
      return;
    }
    if (visible()) ensureCard();
    refresh();
    if (!state.timer) state.timer = window.setInterval(refresh, POLL_MS);
  }

  window.addEventListener("carrot:languagechange", () => {
    document.getElementById(CARD_ID)?.remove();
    sync();
  });
  window.CarrotARS408Settings = { sync, refresh };
})();
