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
void err_fun(double *nom_x, double *delta_x, double *out_6214720069677015676) {
   out_6214720069677015676[0] = delta_x[0] + nom_x[0];
   out_6214720069677015676[1] = delta_x[1] + nom_x[1];
   out_6214720069677015676[2] = delta_x[2] + nom_x[2];
   out_6214720069677015676[3] = delta_x[3] + nom_x[3];
   out_6214720069677015676[4] = delta_x[4] + nom_x[4];
   out_6214720069677015676[5] = delta_x[5] + nom_x[5];
   out_6214720069677015676[6] = delta_x[6] + nom_x[6];
   out_6214720069677015676[7] = delta_x[7] + nom_x[7];
   out_6214720069677015676[8] = delta_x[8] + nom_x[8];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_6538843692110143795) {
   out_6538843692110143795[0] = -nom_x[0] + true_x[0];
   out_6538843692110143795[1] = -nom_x[1] + true_x[1];
   out_6538843692110143795[2] = -nom_x[2] + true_x[2];
   out_6538843692110143795[3] = -nom_x[3] + true_x[3];
   out_6538843692110143795[4] = -nom_x[4] + true_x[4];
   out_6538843692110143795[5] = -nom_x[5] + true_x[5];
   out_6538843692110143795[6] = -nom_x[6] + true_x[6];
   out_6538843692110143795[7] = -nom_x[7] + true_x[7];
   out_6538843692110143795[8] = -nom_x[8] + true_x[8];
}
void H_mod_fun(double *state, double *out_3515170738579258540) {
   out_3515170738579258540[0] = 1.0;
   out_3515170738579258540[1] = 0.0;
   out_3515170738579258540[2] = 0.0;
   out_3515170738579258540[3] = 0.0;
   out_3515170738579258540[4] = 0.0;
   out_3515170738579258540[5] = 0.0;
   out_3515170738579258540[6] = 0.0;
   out_3515170738579258540[7] = 0.0;
   out_3515170738579258540[8] = 0.0;
   out_3515170738579258540[9] = 0.0;
   out_3515170738579258540[10] = 1.0;
   out_3515170738579258540[11] = 0.0;
   out_3515170738579258540[12] = 0.0;
   out_3515170738579258540[13] = 0.0;
   out_3515170738579258540[14] = 0.0;
   out_3515170738579258540[15] = 0.0;
   out_3515170738579258540[16] = 0.0;
   out_3515170738579258540[17] = 0.0;
   out_3515170738579258540[18] = 0.0;
   out_3515170738579258540[19] = 0.0;
   out_3515170738579258540[20] = 1.0;
   out_3515170738579258540[21] = 0.0;
   out_3515170738579258540[22] = 0.0;
   out_3515170738579258540[23] = 0.0;
   out_3515170738579258540[24] = 0.0;
   out_3515170738579258540[25] = 0.0;
   out_3515170738579258540[26] = 0.0;
   out_3515170738579258540[27] = 0.0;
   out_3515170738579258540[28] = 0.0;
   out_3515170738579258540[29] = 0.0;
   out_3515170738579258540[30] = 1.0;
   out_3515170738579258540[31] = 0.0;
   out_3515170738579258540[32] = 0.0;
   out_3515170738579258540[33] = 0.0;
   out_3515170738579258540[34] = 0.0;
   out_3515170738579258540[35] = 0.0;
   out_3515170738579258540[36] = 0.0;
   out_3515170738579258540[37] = 0.0;
   out_3515170738579258540[38] = 0.0;
   out_3515170738579258540[39] = 0.0;
   out_3515170738579258540[40] = 1.0;
   out_3515170738579258540[41] = 0.0;
   out_3515170738579258540[42] = 0.0;
   out_3515170738579258540[43] = 0.0;
   out_3515170738579258540[44] = 0.0;
   out_3515170738579258540[45] = 0.0;
   out_3515170738579258540[46] = 0.0;
   out_3515170738579258540[47] = 0.0;
   out_3515170738579258540[48] = 0.0;
   out_3515170738579258540[49] = 0.0;
   out_3515170738579258540[50] = 1.0;
   out_3515170738579258540[51] = 0.0;
   out_3515170738579258540[52] = 0.0;
   out_3515170738579258540[53] = 0.0;
   out_3515170738579258540[54] = 0.0;
   out_3515170738579258540[55] = 0.0;
   out_3515170738579258540[56] = 0.0;
   out_3515170738579258540[57] = 0.0;
   out_3515170738579258540[58] = 0.0;
   out_3515170738579258540[59] = 0.0;
   out_3515170738579258540[60] = 1.0;
   out_3515170738579258540[61] = 0.0;
   out_3515170738579258540[62] = 0.0;
   out_3515170738579258540[63] = 0.0;
   out_3515170738579258540[64] = 0.0;
   out_3515170738579258540[65] = 0.0;
   out_3515170738579258540[66] = 0.0;
   out_3515170738579258540[67] = 0.0;
   out_3515170738579258540[68] = 0.0;
   out_3515170738579258540[69] = 0.0;
   out_3515170738579258540[70] = 1.0;
   out_3515170738579258540[71] = 0.0;
   out_3515170738579258540[72] = 0.0;
   out_3515170738579258540[73] = 0.0;
   out_3515170738579258540[74] = 0.0;
   out_3515170738579258540[75] = 0.0;
   out_3515170738579258540[76] = 0.0;
   out_3515170738579258540[77] = 0.0;
   out_3515170738579258540[78] = 0.0;
   out_3515170738579258540[79] = 0.0;
   out_3515170738579258540[80] = 1.0;
}
void f_fun(double *state, double dt, double *out_8980226752652779224) {
   out_8980226752652779224[0] = state[0];
   out_8980226752652779224[1] = state[1];
   out_8980226752652779224[2] = state[2];
   out_8980226752652779224[3] = state[3];
   out_8980226752652779224[4] = state[4];
   out_8980226752652779224[5] = dt*((-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]))*state[6] - 9.8100000000000005*state[8] + stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*state[1]) + (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*state[4])) + state[5];
   out_8980226752652779224[6] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*state[4])) + state[6];
   out_8980226752652779224[7] = state[7];
   out_8980226752652779224[8] = state[8];
}
void F_fun(double *state, double dt, double *out_8831106557078054584) {
   out_8831106557078054584[0] = 1;
   out_8831106557078054584[1] = 0;
   out_8831106557078054584[2] = 0;
   out_8831106557078054584[3] = 0;
   out_8831106557078054584[4] = 0;
   out_8831106557078054584[5] = 0;
   out_8831106557078054584[6] = 0;
   out_8831106557078054584[7] = 0;
   out_8831106557078054584[8] = 0;
   out_8831106557078054584[9] = 0;
   out_8831106557078054584[10] = 1;
   out_8831106557078054584[11] = 0;
   out_8831106557078054584[12] = 0;
   out_8831106557078054584[13] = 0;
   out_8831106557078054584[14] = 0;
   out_8831106557078054584[15] = 0;
   out_8831106557078054584[16] = 0;
   out_8831106557078054584[17] = 0;
   out_8831106557078054584[18] = 0;
   out_8831106557078054584[19] = 0;
   out_8831106557078054584[20] = 1;
   out_8831106557078054584[21] = 0;
   out_8831106557078054584[22] = 0;
   out_8831106557078054584[23] = 0;
   out_8831106557078054584[24] = 0;
   out_8831106557078054584[25] = 0;
   out_8831106557078054584[26] = 0;
   out_8831106557078054584[27] = 0;
   out_8831106557078054584[28] = 0;
   out_8831106557078054584[29] = 0;
   out_8831106557078054584[30] = 1;
   out_8831106557078054584[31] = 0;
   out_8831106557078054584[32] = 0;
   out_8831106557078054584[33] = 0;
   out_8831106557078054584[34] = 0;
   out_8831106557078054584[35] = 0;
   out_8831106557078054584[36] = 0;
   out_8831106557078054584[37] = 0;
   out_8831106557078054584[38] = 0;
   out_8831106557078054584[39] = 0;
   out_8831106557078054584[40] = 1;
   out_8831106557078054584[41] = 0;
   out_8831106557078054584[42] = 0;
   out_8831106557078054584[43] = 0;
   out_8831106557078054584[44] = 0;
   out_8831106557078054584[45] = dt*(stiffness_front*(-state[2] - state[3] + state[7])/(mass*state[1]) + (-stiffness_front - stiffness_rear)*state[5]/(mass*state[4]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[6]/(mass*state[4]));
   out_8831106557078054584[46] = -dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*pow(state[1], 2));
   out_8831106557078054584[47] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_8831106557078054584[48] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_8831106557078054584[49] = dt*((-1 - (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*pow(state[4], 2)))*state[6] - (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*pow(state[4], 2)));
   out_8831106557078054584[50] = dt*(-stiffness_front*state[0] - stiffness_rear*state[0])/(mass*state[4]) + 1;
   out_8831106557078054584[51] = dt*(-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]));
   out_8831106557078054584[52] = dt*stiffness_front*state[0]/(mass*state[1]);
   out_8831106557078054584[53] = -9.8100000000000005*dt;
   out_8831106557078054584[54] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front - pow(center_to_rear, 2)*stiffness_rear)*state[6]/(rotational_inertia*state[4]));
   out_8831106557078054584[55] = -center_to_front*dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*pow(state[1], 2));
   out_8831106557078054584[56] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_8831106557078054584[57] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_8831106557078054584[58] = dt*(-(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*pow(state[4], 2)) - (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*pow(state[4], 2)));
   out_8831106557078054584[59] = dt*(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(rotational_inertia*state[4]);
   out_8831106557078054584[60] = dt*(-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])/(rotational_inertia*state[4]) + 1;
   out_8831106557078054584[61] = center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_8831106557078054584[62] = 0;
   out_8831106557078054584[63] = 0;
   out_8831106557078054584[64] = 0;
   out_8831106557078054584[65] = 0;
   out_8831106557078054584[66] = 0;
   out_8831106557078054584[67] = 0;
   out_8831106557078054584[68] = 0;
   out_8831106557078054584[69] = 0;
   out_8831106557078054584[70] = 1;
   out_8831106557078054584[71] = 0;
   out_8831106557078054584[72] = 0;
   out_8831106557078054584[73] = 0;
   out_8831106557078054584[74] = 0;
   out_8831106557078054584[75] = 0;
   out_8831106557078054584[76] = 0;
   out_8831106557078054584[77] = 0;
   out_8831106557078054584[78] = 0;
   out_8831106557078054584[79] = 0;
   out_8831106557078054584[80] = 1;
}
void h_25(double *state, double *unused, double *out_209522151669603385) {
   out_209522151669603385[0] = state[6];
}
void H_25(double *state, double *unused, double *out_1388521086605406300) {
   out_1388521086605406300[0] = 0;
   out_1388521086605406300[1] = 0;
   out_1388521086605406300[2] = 0;
   out_1388521086605406300[3] = 0;
   out_1388521086605406300[4] = 0;
   out_1388521086605406300[5] = 0;
   out_1388521086605406300[6] = 1;
   out_1388521086605406300[7] = 0;
   out_1388521086605406300[8] = 0;
}
void h_24(double *state, double *unused, double *out_8830024610974371563) {
   out_8830024610974371563[0] = state[4];
   out_8830024610974371563[1] = state[5];
}
void H_24(double *state, double *unused, double *out_3565735510212556273) {
   out_3565735510212556273[0] = 0;
   out_3565735510212556273[1] = 0;
   out_3565735510212556273[2] = 0;
   out_3565735510212556273[3] = 0;
   out_3565735510212556273[4] = 1;
   out_3565735510212556273[5] = 0;
   out_3565735510212556273[6] = 0;
   out_3565735510212556273[7] = 0;
   out_3565735510212556273[8] = 0;
   out_3565735510212556273[9] = 0;
   out_3565735510212556273[10] = 0;
   out_3565735510212556273[11] = 0;
   out_3565735510212556273[12] = 0;
   out_3565735510212556273[13] = 0;
   out_3565735510212556273[14] = 1;
   out_3565735510212556273[15] = 0;
   out_3565735510212556273[16] = 0;
   out_3565735510212556273[17] = 0;
}
void h_30(double *state, double *unused, double *out_484716213954109274) {
   out_484716213954109274[0] = state[4];
}
void H_30(double *state, double *unused, double *out_3906854045112654927) {
   out_3906854045112654927[0] = 0;
   out_3906854045112654927[1] = 0;
   out_3906854045112654927[2] = 0;
   out_3906854045112654927[3] = 0;
   out_3906854045112654927[4] = 1;
   out_3906854045112654927[5] = 0;
   out_3906854045112654927[6] = 0;
   out_3906854045112654927[7] = 0;
   out_3906854045112654927[8] = 0;
}
void h_26(double *state, double *unused, double *out_4870865239945066591) {
   out_4870865239945066591[0] = state[7];
}
void H_26(double *state, double *unused, double *out_2352982232268649924) {
   out_2352982232268649924[0] = 0;
   out_2352982232268649924[1] = 0;
   out_2352982232268649924[2] = 0;
   out_2352982232268649924[3] = 0;
   out_2352982232268649924[4] = 0;
   out_2352982232268649924[5] = 0;
   out_2352982232268649924[6] = 0;
   out_2352982232268649924[7] = 1;
   out_2352982232268649924[8] = 0;
}
void h_27(double *state, double *unused, double *out_5852252022750560220) {
   out_5852252022750560220[0] = state[3];
}
void H_27(double *state, double *unused, double *out_6130448116296598144) {
   out_6130448116296598144[0] = 0;
   out_6130448116296598144[1] = 0;
   out_6130448116296598144[2] = 0;
   out_6130448116296598144[3] = 1;
   out_6130448116296598144[4] = 0;
   out_6130448116296598144[5] = 0;
   out_6130448116296598144[6] = 0;
   out_6130448116296598144[7] = 0;
   out_6130448116296598144[8] = 0;
}
void h_29(double *state, double *unused, double *out_8848644947584471380) {
   out_8848644947584471380[0] = state[1];
}
void H_29(double *state, double *unused, double *out_4417085389427047111) {
   out_4417085389427047111[0] = 0;
   out_4417085389427047111[1] = 1;
   out_4417085389427047111[2] = 0;
   out_4417085389427047111[3] = 0;
   out_4417085389427047111[4] = 0;
   out_4417085389427047111[5] = 0;
   out_4417085389427047111[6] = 0;
   out_4417085389427047111[7] = 0;
   out_4417085389427047111[8] = 0;
}
void h_28(double *state, double *unused, double *out_4267685566428786595) {
   out_4267685566428786595[0] = state[0];
}
void H_28(double *state, double *unused, double *out_665313627642483463) {
   out_665313627642483463[0] = 1;
   out_665313627642483463[1] = 0;
   out_665313627642483463[2] = 0;
   out_665313627642483463[3] = 0;
   out_665313627642483463[4] = 0;
   out_665313627642483463[5] = 0;
   out_665313627642483463[6] = 0;
   out_665313627642483463[7] = 0;
   out_665313627642483463[8] = 0;
}
void h_31(double *state, double *unused, double *out_1611486609820060353) {
   out_1611486609820060353[0] = state[8];
}
void H_31(double *state, double *unused, double *out_1419167048482366728) {
   out_1419167048482366728[0] = 0;
   out_1419167048482366728[1] = 0;
   out_1419167048482366728[2] = 0;
   out_1419167048482366728[3] = 0;
   out_1419167048482366728[4] = 0;
   out_1419167048482366728[5] = 0;
   out_1419167048482366728[6] = 0;
   out_1419167048482366728[7] = 0;
   out_1419167048482366728[8] = 1;
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
void car_err_fun(double *nom_x, double *delta_x, double *out_6214720069677015676) {
  err_fun(nom_x, delta_x, out_6214720069677015676);
}
void car_inv_err_fun(double *nom_x, double *true_x, double *out_6538843692110143795) {
  inv_err_fun(nom_x, true_x, out_6538843692110143795);
}
void car_H_mod_fun(double *state, double *out_3515170738579258540) {
  H_mod_fun(state, out_3515170738579258540);
}
void car_f_fun(double *state, double dt, double *out_8980226752652779224) {
  f_fun(state,  dt, out_8980226752652779224);
}
void car_F_fun(double *state, double dt, double *out_8831106557078054584) {
  F_fun(state,  dt, out_8831106557078054584);
}
void car_h_25(double *state, double *unused, double *out_209522151669603385) {
  h_25(state, unused, out_209522151669603385);
}
void car_H_25(double *state, double *unused, double *out_1388521086605406300) {
  H_25(state, unused, out_1388521086605406300);
}
void car_h_24(double *state, double *unused, double *out_8830024610974371563) {
  h_24(state, unused, out_8830024610974371563);
}
void car_H_24(double *state, double *unused, double *out_3565735510212556273) {
  H_24(state, unused, out_3565735510212556273);
}
void car_h_30(double *state, double *unused, double *out_484716213954109274) {
  h_30(state, unused, out_484716213954109274);
}
void car_H_30(double *state, double *unused, double *out_3906854045112654927) {
  H_30(state, unused, out_3906854045112654927);
}
void car_h_26(double *state, double *unused, double *out_4870865239945066591) {
  h_26(state, unused, out_4870865239945066591);
}
void car_H_26(double *state, double *unused, double *out_2352982232268649924) {
  H_26(state, unused, out_2352982232268649924);
}
void car_h_27(double *state, double *unused, double *out_5852252022750560220) {
  h_27(state, unused, out_5852252022750560220);
}
void car_H_27(double *state, double *unused, double *out_6130448116296598144) {
  H_27(state, unused, out_6130448116296598144);
}
void car_h_29(double *state, double *unused, double *out_8848644947584471380) {
  h_29(state, unused, out_8848644947584471380);
}
void car_H_29(double *state, double *unused, double *out_4417085389427047111) {
  H_29(state, unused, out_4417085389427047111);
}
void car_h_28(double *state, double *unused, double *out_4267685566428786595) {
  h_28(state, unused, out_4267685566428786595);
}
void car_H_28(double *state, double *unused, double *out_665313627642483463) {
  H_28(state, unused, out_665313627642483463);
}
void car_h_31(double *state, double *unused, double *out_1611486609820060353) {
  h_31(state, unused, out_1611486609820060353);
}
void car_H_31(double *state, double *unused, double *out_1419167048482366728) {
  H_31(state, unused, out_1419167048482366728);
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
