#pragma once

#include <QPushButton>

#include "selfdrive/ui/ui.h"

const int btn_size = 192;
const int img_size = (btn_size / 4) * 3;

class ExperimentalButton : public QPushButton {
  Q_OBJECT

public:
  explicit ExperimentalButton(QWidget *parent = 0);
  void updateState(const UIState &s);

private:
  void paintEvent(QPaintEvent *event) override;
  void changeMode();

  Params params;
  QPixmap engage_img;
  QPixmap experimental_img;
  bool experimental_mode;
  bool engageable;
};

class MadsButton : public QPushButton {
  Q_OBJECT

public:
  explicit MadsButton(QWidget *parent = 0);
  void updateState(const UIState &s);

private:
  void paintEvent(QPaintEvent *event) override;
  void changeMode();

  Params params;
  bool configured = false;
  bool available = false;
  bool user_enabled = false;
  bool enabled = false;
  bool active = false;
  bool request_pending = false;
  bool requested_enabled = false;
  double request_time = 0.0;
};

void drawIcon(QPainter &p, const QPoint &center, const QPixmap &img, const QBrush &bg, float opacity);
