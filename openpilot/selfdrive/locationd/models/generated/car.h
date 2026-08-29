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
void car_err_fun(double *nom_x, double *delta_x, double *out_6214720069677015676);
void car_inv_err_fun(double *nom_x, double *true_x, double *out_6538843692110143795);
void car_H_mod_fun(double *state, double *out_3515170738579258540);
void car_f_fun(double *state, double dt, double *out_8980226752652779224);
void car_F_fun(double *state, double dt, double *out_8831106557078054584);
void car_h_25(double *state, double *unused, double *out_209522151669603385);
void car_H_25(double *state, double *unused, double *out_1388521086605406300);
void car_h_24(double *state, double *unused, double *out_8830024610974371563);
void car_H_24(double *state, double *unused, double *out_3565735510212556273);
void car_h_30(double *state, double *unused, double *out_484716213954109274);
void car_H_30(double *state, double *unused, double *out_3906854045112654927);
void car_h_26(double *state, double *unused, double *out_4870865239945066591);
void car_H_26(double *state, double *unused, double *out_2352982232268649924);
void car_h_27(double *state, double *unused, double *out_5852252022750560220);
void car_H_27(double *state, double *unused, double *out_6130448116296598144);
void car_h_29(double *state, double *unused, double *out_8848644947584471380);
void car_H_29(double *state, double *unused, double *out_4417085389427047111);
void car_h_28(double *state, double *unused, double *out_4267685566428786595);
void car_H_28(double *state, double *unused, double *out_665313627642483463);
void car_h_31(double *state, double *unused, double *out_1611486609820060353);
void car_H_31(double *state, double *unused, double *out_1419167048482366728);
void car_predict(double *in_x, double *in_P, double *in_Q, double dt);
void car_set_mass(double x);
void car_set_rotational_inertia(double x);
void car_set_center_to_front(double x);
void car_set_center_to_rear(double x);
void car_set_stiffness_front(double x);
void car_set_stiffness_rear(double x);
}