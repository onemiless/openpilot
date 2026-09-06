#include "car.h"

namespace {
#define DIM 9
#define EDIM 9
#define MEDIM 9
typedef void (*Hfun)(double *, double *, double *);

double mass;

void set_mass(double x){ mass = x;}

double rotational_inertia;

void set_rotational_inertia(double x){ rotational_inertia = x;}

double center_to_front;

void set_center_to_front(double x){ center_to_front = x;}

double center_to_rear;

void set_center_to_rear(double x){ center_to_rear = x;}

double stiffness_front;

void set_stiffness_front(double x){ stiffness_front = x;}

double stiffness_rear;

void set_stiffness_rear(double x){ stiffness_rear = x;}
const static double MAHA_THRESH_25 = 3.8414588206941227;
const static double MAHA_THRESH_24 = 5.991464547107981;
const static double MAHA_THRESH_30 = 3.8414588206941227;
const static double MAHA_THRESH_26 = 3.8414588206941227;
const static double MAHA_THRESH_27 = 3.8414588206941227;
const static double MAHA_THRESH_29 = 3.8414588206941227;
const static double MAHA_THRESH_28 = 3.8414588206941227;
const static double MAHA_THRESH_31 = 3.8414588206941227;

/******************************************************************************
 *                      Code generated with SymPy 1.14.0                      *
 *                                                                            *
 *              See http://www.sympy.org/ for more information.               *
 *                                                                            *
 *                         This file is part of 'ekf'                         *
 ******************************************************************************/
void err_fun(double *nom_x, double *delta_x, double *out_5173364757374056855) {
   out_5173364757374056855[0] = delta_x[0] + nom_x[0];
   out_5173364757374056855[1] = delta_x[1] + nom_x[1];
   out_5173364757374056855[2] = delta_x[2] + nom_x[2];
   out_5173364757374056855[3] = delta_x[3] + nom_x[3];
   out_5173364757374056855[4] = delta_x[4] + nom_x[4];
   out_5173364757374056855[5] = delta_x[5] + nom_x[5];
   out_5173364757374056855[6] = delta_x[6] + nom_x[6];
   out_5173364757374056855[7] = delta_x[7] + nom_x[7];
   out_5173364757374056855[8] = delta_x[8] + nom_x[8];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_8548956718453099010) {
   out_8548956718453099010[0] = -nom_x[0] + true_x[0];
   out_8548956718453099010[1] = -nom_x[1] + true_x[1];
   out_8548956718453099010[2] = -nom_x[2] + true_x[2];
   out_8548956718453099010[3] = -nom_x[3] + true_x[3];
   out_8548956718453099010[4] = -nom_x[4] + true_x[4];
   out_8548956718453099010[5] = -nom_x[5] + true_x[5];
   out_8548956718453099010[6] = -nom_x[6] + true_x[6];
   out_8548956718453099010[7] = -nom_x[7] + true_x[7];
   out_8548956718453099010[8] = -nom_x[8] + true_x[8];
}
void H_mod_fun(double *state, double *out_3277610141978184460) {
   out_3277610141978184460[0] = 1.0;
   out_3277610141978184460[1] = 0.0;
   out_3277610141978184460[2] = 0.0;
   out_3277610141978184460[3] = 0.0;
   out_3277610141978184460[4] = 0.0;
   out_3277610141978184460[5] = 0.0;
   out_3277610141978184460[6] = 0.0;
   out_3277610141978184460[7] = 0.0;
   out_3277610141978184460[8] = 0.0;
   out_3277610141978184460[9] = 0.0;
   out_3277610141978184460[10] = 1.0;
   out_3277610141978184460[11] = 0.0;
   out_3277610141978184460[12] = 0.0;
   out_3277610141978184460[13] = 0.0;
   out_3277610141978184460[14] = 0.0;
   out_3277610141978184460[15] = 0.0;
   out_3277610141978184460[16] = 0.0;
   out_3277610141978184460[17] = 0.0;
   out_3277610141978184460[18] = 0.0;
   out_3277610141978184460[19] = 0.0;
   out_3277610141978184460[20] = 1.0;
   out_3277610141978184460[21] = 0.0;
   out_3277610141978184460[22] = 0.0;
   out_3277610141978184460[23] = 0.0;
   out_3277610141978184460[24] = 0.0;
   out_3277610141978184460[25] = 0.0;
   out_3277610141978184460[26] = 0.0;
   out_3277610141978184460[27] = 0.0;
   out_3277610141978184460[28] = 0.0;
   out_3277610141978184460[29] = 0.0;
   out_3277610141978184460[30] = 1.0;
   out_3277610141978184460[31] = 0.0;
   out_3277610141978184460[32] = 0.0;
   out_3277610141978184460[33] = 0.0;
   out_3277610141978184460[34] = 0.0;
   out_3277610141978184460[35] = 0.0;
   out_3277610141978184460[36] = 0.0;
   out_3277610141978184460[37] = 0.0;
   out_3277610141978184460[38] = 0.0;
   out_3277610141978184460[39] = 0.0;
   out_3277610141978184460[40] = 1.0;
   out_3277610141978184460[41] = 0.0;
   out_3277610141978184460[42] = 0.0;
   out_3277610141978184460[43] = 0.0;
   out_3277610141978184460[44] = 0.0;
   out_3277610141978184460[45] = 0.0;
   out_3277610141978184460[46] = 0.0;
   out_3277610141978184460[47] = 0.0;
   out_3277610141978184460[48] = 0.0;
   out_3277610141978184460[49] = 0.0;
   out_3277610141978184460[50] = 1.0;
   out_3277610141978184460[51] = 0.0;
   out_3277610141978184460[52] = 0.0;
   out_3277610141978184460[53] = 0.0;
   out_3277610141978184460[54] = 0.0;
   out_3277610141978184460[55] = 0.0;
   out_3277610141978184460[56] = 0.0;
   out_3277610141978184460[57] = 0.0;
   out_3277610141978184460[58] = 0.0;
   out_3277610141978184460[59] = 0.0;
   out_3277610141978184460[60] = 1.0;
   out_3277610141978184460[61] = 0.0;
   out_3277610141978184460[62] = 0.0;
   out_3277610141978184460[63] = 0.0;
   out_3277610141978184460[64] = 0.0;
   out_3277610141978184460[65] = 0.0;
   out_3277610141978184460[66] = 0.0;
   out_3277610141978184460[67] = 0.0;
   out_3277610141978184460[68] = 0.0;
   out_3277610141978184460[69] = 0.0;
   out_3277610141978184460[70] = 1.0;
   out_3277610141978184460[71] = 0.0;
   out_3277610141978184460[72] = 0.0;
   out_3277610141978184460[73] = 0.0;
   out_3277610141978184460[74] = 0.0;
   out_3277610141978184460[75] = 0.0;
   out_3277610141978184460[76] = 0.0;
   out_3277610141978184460[77] = 0.0;
   out_3277610141978184460[78] = 0.0;
   out_3277610141978184460[79] = 0.0;
   out_3277610141978184460[80] = 1.0;
}
void f_fun(double *state, double dt, double *out_1962236870283003500) {
   out_1962236870283003500[0] = state[0];
   out_1962236870283003500[1] = state[1];
   out_1962236870283003500[2] = state[2];
   out_1962236870283003500[3] = state[3];
   out_1962236870283003500[4] = state[4];
   out_1962236870283003500[5] = dt*((-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]))*state[6] - 9.8100000000000005*state[8] + stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*state[1]) + (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*state[4])) + state[5];
   out_1962236870283003500[6] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*state[4])) + state[6];
   out_1962236870283003500[7] = state[7];
   out_1962236870283003500[8] = state[8];
}
void F_fun(double *state, double dt, double *out_37680120949772078) {
   out_37680120949772078[0] = 1;
   out_37680120949772078[1] = 0;
   out_37680120949772078[2] = 0;
   out_37680120949772078[3] = 0;
   out_37680120949772078[4] = 0;
   out_37680120949772078[5] = 0;
   out_37680120949772078[6] = 0;
   out_37680120949772078[7] = 0;
   out_37680120949772078[8] = 0;
   out_37680120949772078[9] = 0;
   out_37680120949772078[10] = 1;
   out_37680120949772078[11] = 0;
   out_37680120949772078[12] = 0;
   out_37680120949772078[13] = 0;
   out_37680120949772078[14] = 0;
   out_37680120949772078[15] = 0;
   out_37680120949772078[16] = 0;
   out_37680120949772078[17] = 0;
   out_37680120949772078[18] = 0;
   out_37680120949772078[19] = 0;
   out_37680120949772078[20] = 1;
   out_37680120949772078[21] = 0;
   out_37680120949772078[22] = 0;
   out_37680120949772078[23] = 0;
   out_37680120949772078[24] = 0;
   out_37680120949772078[25] = 0;
   out_37680120949772078[26] = 0;
   out_37680120949772078[27] = 0;
   out_37680120949772078[28] = 0;
   out_37680120949772078[29] = 0;
   out_37680120949772078[30] = 1;
   out_37680120949772078[31] = 0;
   out_37680120949772078[32] = 0;
   out_37680120949772078[33] = 0;
   out_37680120949772078[34] = 0;
   out_37680120949772078[35] = 0;
   out_37680120949772078[36] = 0;
   out_37680120949772078[37] = 0;
   out_37680120949772078[38] = 0;
   out_37680120949772078[39] = 0;
   out_37680120949772078[40] = 1;
   out_37680120949772078[41] = 0;
   out_37680120949772078[42] = 0;
   out_37680120949772078[43] = 0;
   out_37680120949772078[44] = 0;
   out_37680120949772078[45] = dt*(stiffness_front*(-state[2] - state[3] + state[7])/(mass*state[1]) + (-stiffness_front - stiffness_rear)*state[5]/(mass*state[4]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[6]/(mass*state[4]));
   out_37680120949772078[46] = -dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*pow(state[1], 2));
   out_37680120949772078[47] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_37680120949772078[48] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_37680120949772078[49] = dt*((-1 - (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*pow(state[4], 2)))*state[6] - (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*pow(state[4], 2)));
   out_37680120949772078[50] = dt*(-stiffness_front*state[0] - stiffness_rear*state[0])/(mass*state[4]) + 1;
   out_37680120949772078[51] = dt*(-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]));
   out_37680120949772078[52] = dt*stiffness_front*state[0]/(mass*state[1]);
   out_37680120949772078[53] = -9.8100000000000005*dt;
   out_37680120949772078[54] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front - pow(center_to_rear, 2)*stiffness_rear)*state[6]/(rotational_inertia*state[4]));
   out_37680120949772078[55] = -center_to_front*dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*pow(state[1], 2));
   out_37680120949772078[56] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_37680120949772078[57] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_37680120949772078[58] = dt*(-(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*pow(state[4], 2)) - (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*pow(state[4], 2)));
   out_37680120949772078[59] = dt*(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(rotational_inertia*state[4]);
   out_37680120949772078[60] = dt*(-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])/(rotational_inertia*state[4]) + 1;
   out_37680120949772078[61] = center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_37680120949772078[62] = 0;
   out_37680120949772078[63] = 0;
   out_37680120949772078[64] = 0;
   out_37680120949772078[65] = 0;
   out_37680120949772078[66] = 0;
   out_37680120949772078[67] = 0;
   out_37680120949772078[68] = 0;
   out_37680120949772078[69] = 0;
   out_37680120949772078[70] = 1;
   out_37680120949772078[71] = 0;
   out_37680120949772078[72] = 0;
   out_37680120949772078[73] = 0;
   out_37680120949772078[74] = 0;
   out_37680120949772078[75] = 0;
   out_37680120949772078[76] = 0;
   out_37680120949772078[77] = 0;
   out_37680120949772078[78] = 0;
   out_37680120949772078[79] = 0;
   out_37680120949772078[80] = 1;
}
void h_25(double *state, double *unused, double *out_560717135288700913) {
   out_560717135288700913[0] = state[6];
}
void H_25(double *state, double *unused, double *out_8672110971841337205) {
   out_8672110971841337205[0] = 0;
   out_8672110971841337205[1] = 0;
   out_8672110971841337205[2] = 0;
   out_8672110971841337205[3] = 0;
   out_8672110971841337205[4] = 0;
   out_8672110971841337205[5] = 0;
   out_8672110971841337205[6] = 1;
   out_8672110971841337205[7] = 0;
   out_8672110971841337205[8] = 0;
}
void h_24(double *state, double *unused, double *out_4929302868998112570) {
   out_4929302868998112570[0] = state[4];
   out_4929302868998112570[1] = state[5];
}
void H_24(double *state, double *unused, double *out_2471078291990175779) {
   out_2471078291990175779[0] = 0;
   out_2471078291990175779[1] = 0;
   out_2471078291990175779[2] = 0;
   out_2471078291990175779[3] = 0;
   out_2471078291990175779[4] = 1;
   out_2471078291990175779[5] = 0;
   out_2471078291990175779[6] = 0;
   out_2471078291990175779[7] = 0;
   out_2471078291990175779[8] = 0;
   out_2471078291990175779[9] = 0;
   out_2471078291990175779[10] = 0;
   out_2471078291990175779[11] = 0;
   out_2471078291990175779[12] = 0;
   out_2471078291990175779[13] = 0;
   out_2471078291990175779[14] = 1;
   out_2471078291990175779[15] = 0;
   out_2471078291990175779[16] = 0;
   out_2471078291990175779[17] = 0;
}
void h_30(double *state, double *unused, double *out_3076732392965321437) {
   out_3076732392965321437[0] = state[4];
}
void H_30(double *state, double *unused, double *out_8542772024698097135) {
   out_8542772024698097135[0] = 0;
   out_8542772024698097135[1] = 0;
   out_8542772024698097135[2] = 0;
   out_8542772024698097135[3] = 0;
   out_8542772024698097135[4] = 1;
   out_8542772024698097135[5] = 0;
   out_8542772024698097135[6] = 0;
   out_8542772024698097135[7] = 0;
   out_8542772024698097135[8] = 0;
}
void h_26(double *state, double *unused, double *out_6717239630788870755) {
   out_6717239630788870755[0] = state[7];
}
void H_26(double *state, double *unused, double *out_4930607652967280981) {
   out_4930607652967280981[0] = 0;
   out_4930607652967280981[1] = 0;
   out_4930607652967280981[2] = 0;
   out_4930607652967280981[3] = 0;
   out_4930607652967280981[4] = 0;
   out_4930607652967280981[5] = 0;
   out_4930607652967280981[6] = 0;
   out_4930607652967280981[7] = 1;
   out_4930607652967280981[8] = 0;
}
void h_27(double *state, double *unused, double *out_1504226988190363348) {
   out_1504226988190363348[0] = state[3];
}
void H_27(double *state, double *unused, double *out_6368008712897672224) {
   out_6368008712897672224[0] = 0;
   out_6368008712897672224[1] = 0;
   out_6368008712897672224[2] = 0;
   out_6368008712897672224[3] = 1;
   out_6368008712897672224[4] = 0;
   out_6368008712897672224[5] = 0;
   out_6368008712897672224[6] = 0;
   out_6368008712897672224[7] = 0;
   out_6368008712897672224[8] = 0;
}
void h_29(double *state, double *unused, double *out_1661413656541492493) {
   out_1661413656541492493[0] = state[1];
}
void H_29(double *state, double *unused, double *out_4654645986028121191) {
   out_4654645986028121191[0] = 0;
   out_4654645986028121191[1] = 1;
   out_4654645986028121191[2] = 0;
   out_4654645986028121191[3] = 0;
   out_4654645986028121191[4] = 0;
   out_4654645986028121191[5] = 0;
   out_4654645986028121191[6] = 0;
   out_4654645986028121191[7] = 0;
   out_4654645986028121191[8] = 0;
}
void h_28(double *state, double *unused, double *out_4541013039634696033) {
   out_4541013039634696033[0] = state[0];
}
void H_28(double *state, double *unused, double *out_427753031041409383) {
   out_427753031041409383[0] = 1;
   out_427753031041409383[1] = 0;
   out_427753031041409383[2] = 0;
   out_427753031041409383[3] = 0;
   out_427753031041409383[4] = 0;
   out_427753031041409383[5] = 0;
   out_427753031041409383[6] = 0;
   out_427753031041409383[7] = 0;
   out_427753031041409383[8] = 0;
}
void h_31(double *state, double *unused, double *out_6781094318135714882) {
   out_6781094318135714882[0] = state[8];
}
void H_31(double *state, double *unused, double *out_8702756933718297633) {
   out_8702756933718297633[0] = 0;
   out_8702756933718297633[1] = 0;
   out_8702756933718297633[2] = 0;
   out_8702756933718297633[3] = 0;
   out_8702756933718297633[4] = 0;
   out_8702756933718297633[5] = 0;
   out_8702756933718297633[6] = 0;
   out_8702756933718297633[7] = 0;
   out_8702756933718297633[8] = 1;
}
#include <eigen3/Eigen/Dense>
#include <iostream>

typedef Eigen::Matrix<double, DIM, DIM, Eigen::RowMajor> DDM;
typedef Eigen::Matrix<double, EDIM, EDIM, Eigen::RowMajor> EEM;
typedef Eigen::Matrix<double, DIM, EDIM, Eigen::RowMajor> DEM;

void predict(double *in_x, double *in_P, double *in_Q, double dt) {
  typedef Eigen::Matrix<double, MEDIM, MEDIM, Eigen::RowMajor> RRM;

  double nx[DIM] = {0};
  double in_F[EDIM*EDIM] = {0};

  // functions from sympy
  f_fun(in_x, dt, nx);
  F_fun(in_x, dt, in_F);


  EEM F(in_F);
  EEM P(in_P);
  EEM Q(in_Q);

  RRM F_main = F.topLeftCorner(MEDIM, MEDIM);
  P.topLeftCorner(MEDIM, MEDIM) = (F_main * P.topLeftCorner(MEDIM, MEDIM)) * F_main.transpose();
  P.topRightCorner(MEDIM, EDIM - MEDIM) = F_main * P.topRightCorner(MEDIM, EDIM - MEDIM);
  P.bottomLeftCorner(EDIM - MEDIM, MEDIM) = P.bottomLeftCorner(EDIM - MEDIM, MEDIM) * F_main.transpose();

  P = P + dt*Q;

  // copy out state
  memcpy(in_x, nx, DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
}

// note: extra_args dim only correct when null space projecting
// otherwise 1
template <int ZDIM, int EADIM, bool MAHA_TEST>
void update(double *in_x, double *in_P, Hfun h_fun, Hfun H_fun, Hfun Hea_fun, double *in_z, double *in_R, double *in_ea, double MAHA_THRESHOLD) {
  typedef Eigen::Matrix<double, ZDIM, ZDIM, Eigen::RowMajor> ZZM;
  typedef Eigen::Matrix<double, ZDIM, DIM, Eigen::RowMajor> ZDM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, EDIM, Eigen::RowMajor> XEM;
  //typedef Eigen::Matrix<double, EDIM, ZDIM, Eigen::RowMajor> EZM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, 1> X1M;
  typedef Eigen::Matrix<double, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor> XXM;

  double in_hx[ZDIM] = {0};
  double in_H[ZDIM * DIM] = {0};
  double in_H_mod[EDIM * DIM] = {0};
  double delta_x[EDIM] = {0};
  double x_new[DIM] = {0};


  // state x, P
  Eigen::Matrix<double, ZDIM, 1> z(in_z);
  EEM P(in_P);
  ZZM pre_R(in_R);

  // functions from sympy
  h_fun(in_x, in_ea, in_hx);
  H_fun(in_x, in_ea, in_H);
  ZDM pre_H(in_H);

  // get y (y = z - hx)
  Eigen::Matrix<double, ZDIM, 1> pre_y(in_hx); pre_y = z - pre_y;
  X1M y; XXM H; XXM R;
  if (Hea_fun){
    typedef Eigen::Matrix<double, ZDIM, EADIM, Eigen::RowMajor> ZAM;
    double in_Hea[ZDIM * EADIM] = {0};
    Hea_fun(in_x, in_ea, in_Hea);
    ZAM Hea(in_Hea);
    XXM A = Hea.transpose().fullPivLu().kernel();


    y = A.transpose() * pre_y;
    H = A.transpose() * pre_H;
    R = A.transpose() * pre_R * A;
  } else {
    y = pre_y;
    H = pre_H;
    R = pre_R;
  }
  // get modified H
  H_mod_fun(in_x, in_H_mod);
  DEM H_mod(in_H_mod);
  XEM H_err = H * H_mod;

  // Do mahalobis distance test
  if (MAHA_TEST){
    XXM a = (H_err * P * H_err.transpose() + R).inverse();
    double maha_dist = y.transpose() * a * y;
    if (maha_dist > MAHA_THRESHOLD){
      R = 1.0e16 * R;
    }
  }

  // Outlier resilient weighting
  double weight = 1;//(1.5)/(1 + y.squaredNorm()/R.sum());

  // kalman gains and I_KH
  XXM S = ((H_err * P) * H_err.transpose()) + R/weight;
  XEM KT = S.fullPivLu().solve(H_err * P.transpose());
  //EZM K = KT.transpose(); TODO: WHY DOES THIS NOT COMPILE?
  //EZM K = S.fullPivLu().solve(H_err * P.transpose()).transpose();
  //std::cout << "Here is the matrix rot:\n" << K << std::endl;
  EEM I_KH = Eigen::Matrix<double, EDIM, EDIM>::Identity() - (KT.transpose() * H_err);

  // update state by injecting dx
  Eigen::Matrix<double, EDIM, 1> dx(delta_x);
  dx  = (KT.transpose() * y);
  memcpy(delta_x, dx.data(), EDIM * sizeof(double));
  err_fun(in_x, delta_x, x_new);
  Eigen::Matrix<double, DIM, 1> x(x_new);

  // update cov
  P = ((I_KH * P) * I_KH.transpose()) + ((KT.transpose() * R) * KT);

  // copy out state
  memcpy(in_x, x.data(), DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
  memcpy(in_z, y.data(), y.rows() * sizeof(double));
}




}
extern "C" {

void car_update_25(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_25, H_25, NULL, in_z, in_R, in_ea, MAHA_THRESH_25);
}
void car_update_24(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<2, 3, 0>(in_x, in_P, h_24, H_24, NULL, in_z, in_R, in_ea, MAHA_THRESH_24);
}
void car_update_30(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_30, H_30, NULL, in_z, in_R, in_ea, MAHA_THRESH_30);
}
void car_update_26(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_26, H_26, NULL, in_z, in_R, in_ea, MAHA_THRESH_26);
}
void car_update_27(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_27, H_27, NULL, in_z, in_R, in_ea, MAHA_THRESH_27);
}
void car_update_29(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_29, H_29, NULL, in_z, in_R, in_ea, MAHA_THRESH_29);
}
void car_update_28(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_28, H_28, NULL, in_z, in_R, in_ea, MAHA_THRESH_28);
}
void car_update_31(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_31, H_31, NULL, in_z, in_R, in_ea, MAHA_THRESH_31);
}
void car_err_fun(double *nom_x, double *delta_x, double *out_5173364757374056855) {
  err_fun(nom_x, delta_x, out_5173364757374056855);
}
void car_inv_err_fun(double *nom_x, double *true_x, double *out_8548956718453099010) {
  inv_err_fun(nom_x, true_x, out_8548956718453099010);
}
void car_H_mod_fun(double *state, double *out_3277610141978184460) {
  H_mod_fun(state, out_3277610141978184460);
}
void car_f_fun(double *state, double dt, double *out_1962236870283003500) {
  f_fun(state,  dt, out_1962236870283003500);
}
void car_F_fun(double *state, double dt, double *out_37680120949772078) {
  F_fun(state,  dt, out_37680120949772078);
}
void car_h_25(double *state, double *unused, double *out_560717135288700913) {
  h_25(state, unused, out_560717135288700913);
}
void car_H_25(double *state, double *unused, double *out_8672110971841337205) {
  H_25(state, unused, out_8672110971841337205);
}
void car_h_24(double *state, double *unused, double *out_4929302868998112570) {
  h_24(state, unused, out_4929302868998112570);
}
void car_H_24(double *state, double *unused, double *out_2471078291990175779) {
  H_24(state, unused, out_2471078291990175779);
}
void car_h_30(double *state, double *unused, double *out_3076732392965321437) {
  h_30(state, unused, out_3076732392965321437);
}
void car_H_30(double *state, double *unused, double *out_8542772024698097135) {
  H_30(state, unused, out_8542772024698097135);
}
void car_h_26(double *state, double *unused, double *out_6717239630788870755) {
  h_26(state, unused, out_6717239630788870755);
}
void car_H_26(double *state, double *unused, double *out_4930607652967280981) {
  H_26(state, unused, out_4930607652967280981);
}
void car_h_27(double *state, double *unused, double *out_1504226988190363348) {
  h_27(state, unused, out_1504226988190363348);
}
void car_H_27(double *state, double *unused, double *out_6368008712897672224) {
  H_27(state, unused, out_6368008712897672224);
}
void car_h_29(double *state, double *unused, double *out_1661413656541492493) {
  h_29(state, unused, out_1661413656541492493);
}
void car_H_29(double *state, double *unused, double *out_4654645986028121191) {
  H_29(state, unused, out_4654645986028121191);
}
void car_h_28(double *state, double *unused, double *out_4541013039634696033) {
  h_28(state, unused, out_4541013039634696033);
}
void car_H_28(double *state, double *unused, double *out_427753031041409383) {
  H_28(state, unused, out_427753031041409383);
}
void car_h_31(double *state, double *unused, double *out_6781094318135714882) {
  h_31(state, unused, out_6781094318135714882);
}
void car_H_31(double *state, double *unused, double *out_8702756933718297633) {
  H_31(state, unused, out_8702756933718297633);
}
void car_predict(double *in_x, double *in_P, double *in_Q, double dt) {
  predict(in_x, in_P, in_Q, dt);
}
void car_set_mass(double x) {
  set_mass(x);
}
void car_set_rotational_inertia(double x) {
  set_rotational_inertia(x);
}
void car_set_center_to_front(double x) {
  set_center_to_front(x);
}
void car_set_center_to_rear(double x) {
  set_center_to_rear(x);
}
void car_set_stiffness_front(double x) {
  set_stiffness_front(x);
}
void car_set_stiffness_rear(double x) {
  set_stiffness_rear(x);
}
}

const EKF car = {
  .name = "car",
  .kinds = { 25, 24, 30, 26, 27, 29, 28, 31 },
  .feature_kinds = {  },
  .f_fun = car_f_fun,
  .F_fun = car_F_fun,
  .err_fun = car_err_fun,
  .inv_err_fun = car_inv_err_fun,
  .H_mod_fun = car_H_mod_fun,
  .predict = car_predict,
  .hs = {
    { 25, car_h_25 },
    { 24, car_h_24 },
    { 30, car_h_30 },
    { 26, car_h_26 },
    { 27, car_h_27 },
    { 29, car_h_29 },
    { 28, car_h_28 },
    { 31, car_h_31 },
  },
  .Hs = {
    { 25, car_H_25 },
    { 24, car_H_24 },
    { 30, car_H_30 },
    { 26, car_H_26 },
    { 27, car_H_27 },
    { 29, car_H_29 },
    { 28, car_H_28 },
    { 31, car_H_31 },
  },
  .updates = {
    { 25, car_update_25 },
    { 24, car_update_24 },
    { 30, car_update_30 },
    { 26, car_update_26 },
    { 27, car_update_27 },
    { 29, car_update_29 },
    { 28, car_update_28 },
    { 31, car_update_31 },
  },
  .Hes = {
  },
  .sets = {
    { "mass", car_set_mass },
    { "rotational_inertia", car_set_rotational_inertia },
    { "center_to_front", car_set_center_to_front },
    { "center_to_rear", car_set_center_to_rear },
    { "stiffness_front", car_set_stiffness_front },
    { "stiffness_rear", car_set_stiffness_rear },
  },
  .extra_routines = {
  },
};

ekf_lib_init(car)
