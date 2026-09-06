#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void car_update_25(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_24(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_30(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_26(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_27(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_29(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_28(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_31(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_err_fun(double *nom_x, double *delta_x, double *out_5173364757374056855);
void car_inv_err_fun(double *nom_x, double *true_x, double *out_8548956718453099010);
void car_H_mod_fun(double *state, double *out_3277610141978184460);
void car_f_fun(double *state, double dt, double *out_1962236870283003500);
void car_F_fun(double *state, double dt, double *out_37680120949772078);
void car_h_25(double *state, double *unused, double *out_560717135288700913);
void car_H_25(double *state, double *unused, double *out_8672110971841337205);
void car_h_24(double *state, double *unused, double *out_4929302868998112570);
void car_H_24(double *state, double *unused, double *out_2471078291990175779);
void car_h_30(double *state, double *unused, double *out_3076732392965321437);
void car_H_30(double *state, double *unused, double *out_8542772024698097135);
void car_h_26(double *state, double *unused, double *out_6717239630788870755);
void car_H_26(double *state, double *unused, double *out_4930607652967280981);
void car_h_27(double *state, double *unused, double *out_1504226988190363348);
void car_H_27(double *state, double *unused, double *out_6368008712897672224);
void car_h_29(double *state, double *unused, double *out_1661413656541492493);
void car_H_29(double *state, double *unused, double *out_4654645986028121191);
void car_h_28(double *state, double *unused, double *out_4541013039634696033);
void car_H_28(double *state, double *unused, double *out_427753031041409383);
void car_h_31(double *state, double *unused, double *out_6781094318135714882);
void car_H_31(double *state, double *unused, double *out_8702756933718297633);
void car_predict(double *in_x, double *in_P, double *in_Q, double dt);
void car_set_mass(double x);
void car_set_rotational_inertia(double x);
void car_set_center_to_front(double x);
void car_set_center_to_rear(double x);
void car_set_stiffness_front(double x);
void car_set_stiffness_rear(double x);
}