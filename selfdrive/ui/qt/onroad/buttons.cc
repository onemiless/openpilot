#include "selfdrive/ui/qt/onroad/buttons.h"

#include <QPainter>

#include "common/swaglog.h"
#include "selfdrive/ui/qt/util.h"

void drawIcon(QPainter &p, const QPoint &center, const QPixmap &img, const QBrush &bg, float opacity) {
  p.setRenderHint(QPainter::Antialiasing);
  p.setOpacity(1.0);  // bg dictates opacity of ellipse
  p.setPen(Qt::NoPen);
  p.setBrush(bg);
  p.drawEllipse(center, btn_size / 2, btn_size / 2);
  p.setOpacity(opacity);
  p.drawPixmap(center - QPoint(img.width() / 2, img.height() / 2), img);
  p.setOpacity(1.0);
}

// ExperimentalButton
ExperimentalButton::ExperimentalButton(QWidget *parent) : experimental_mode(false), engageable(false), QPushButton(parent) {
  setFixedSize(btn_size, btn_size);

  engage_img = loadPixmap("../assets/img_chffr_wheel.png", {img_size, img_size});
  experimental_img = loadPixmap("../assets/img_experimental.svg", {img_size, img_size});
  QObject::connect(this, &QPushButton::clicked, this, &ExperimentalButton::changeMode);
}

void ExperimentalButton::changeMode() {
  const auto cp = (*uiState()->sm)["carParams"].getCarParams();
  bool can_change = hasLongitudinalControl(cp) && params.getBool("ExperimentalModeConfirmed");
  if (can_change) {
    params.putBool("ExperimentalMode", !experimental_mode);
  }
}

void ExperimentalButton::updateState(const UIState &s) {
  const auto cs = (*s.sm)["selfdriveState"].getSelfdriveState();
  bool eng = cs.getEngageable() || cs.getEnabled();
  if ((s.scene.carrot_experimental_mode != experimental_mode) || (eng != engageable)) {
    engageable = eng;
    experimental_mode = cs.getExperimentalMode();
    experimental_mode |= s.scene.carrot_experimental_mode;
    update();
  }
}

void ExperimentalButton::paintEvent(QPaintEvent *event) {
  QPainter p(this);
  QPixmap img = experimental_mode ? experimental_img : engage_img;
  drawIcon(p, QPoint(btn_size / 2, btn_size / 2), img, QColor(0, 0, 0, 1), (isDown() || !engageable) ? 0.6 : 1.0);
}

MadsButton::MadsButton(QWidget *parent) : QPushButton(parent) {
  setFixedSize(btn_size, btn_size);
  setVisible(false);
  QObject::connect(this, &QPushButton::clicked, this, &MadsButton::changeMode);
}

void MadsButton::changeMode() {
  if (!available) {
    return;
  }

  requested_enabled = !user_enabled;
  request_pending = true;
  request_time = millis_since_boot();
  params.putBoolNonBlocking("MadsUserEnabled", requested_enabled);
  LOGW("MADS UI request user_enabled=%d current_enabled=%d active=%d",
       requested_enabled, enabled, active);
  update();
}

void MadsButton::updateState(const UIState &s) {
  const SubMaster &sm = *(s.sm);
  const bool tesla = sm["carParams"].getCarParams().getBrand() == "tesla";
  const auto mads = sm["madsState"].getMadsState();

  const bool configured_new = mads.getConfigured();
  const bool available_new = mads.getAvailable();
  const bool user_enabled_new = mads.getUserEnabled();
  const bool enabled_new = mads.getEnabled();
  const bool active_new = mads.getActive();

  if (request_pending) {
    const double elapsed = millis_since_boot() - request_time;
    if (user_enabled_new == requested_enabled) {
      LOGW("MADS UI request acknowledged user_enabled=%d latency_ms=%.0f", requested_enabled, elapsed);
      request_pending = false;
    } else if (elapsed > 1000.0) {
      LOGE("MADS UI request timeout requested=%d actual=%d", requested_enabled, user_enabled_new);
      request_pending = false;
    }
  }

  const bool changed = configured != configured_new || available != available_new ||
                       user_enabled != user_enabled_new || enabled != enabled_new || active != active_new;
  configured = configured_new;
  available = available_new;
  user_enabled = user_enabled_new;
  enabled = enabled_new;
  active = active_new;

  setVisible(tesla && configured);
  setEnabled(available);
  if (changed) {
    update();
  }
}

void MadsButton::paintEvent(QPaintEvent *event) {
  QPainter p(this);
  p.setRenderHint(QPainter::Antialiasing);
  p.setPen(QPen(QColor(255, 255, 255, available ? 220 : 90), 5));

  QColor background(55, 55, 55, 210);
  QString state_text = QStringLiteral("关闭");
  if (request_pending) {
    background = requested_enabled ? QColor(184, 134, 11, 230) : QColor(90, 90, 90, 230);
    state_text = requested_enabled ? QStringLiteral("待确认") : QStringLiteral("关闭中");
  } else if (enabled) {
    background = active ? QColor(23, 134, 68, 235) : QColor(111, 192, 201, 235);
    state_text = active ? QStringLiteral("开启") : QStringLiteral("暂停");
  } else if (user_enabled) {
    background = QColor(184, 134, 11, 230);
    state_text = QStringLiteral("待启用");
  }

  p.setBrush(background);
  p.drawEllipse(rect().adjusted(5, 5, -5, -5));
  p.setPen(QColor(255, 255, 255, available ? 255 : 100));
  QFont title_font = p.font();
  title_font.setBold(true);
  title_font.setPixelSize(42);
  p.setFont(title_font);
  p.drawText(QRect(0, 38, width(), 55), Qt::AlignCenter, "MADS");
  QFont state_font = p.font();
  state_font.setPixelSize(30);
  p.setFont(state_font);
  p.drawText(QRect(0, 96, width(), 48), Qt::AlignCenter, state_text);
}
