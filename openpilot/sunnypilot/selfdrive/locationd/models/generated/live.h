#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void live_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_9(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_12(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_35(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_32(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_33(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_H(double *in_vec, double *out_8998864312083674865);
void live_err_fun(double *nom_x, double *delta_x, double *out_2653138292238438681);
void live_inv_err_fun(double *nom_x, double *true_x, double *out_1445903288115546050);
void live_H_mod_fun(double *state, double *out_4258670010172105806);
void live_f_fun(double *state, double dt, double *out_143103317738967059);
void live_F_fun(double *state, double dt, double *out_7892539495548121978);
void live_h_4(double *state, double *unused, double *out_4075958995006781438);
void live_H_4(double *state, double *unused, double *out_1232583429978071990);
void live_h_9(double *state, double *unused, double *out_7515695079624580786);
void live_H_9(double *state, double *unused, double *out_991393783348481345);
void live_h_10(double *state, double *unused, double *out_2984504588913036619);
void live_H_10(double *state, double *unused, double *out_3377667081354262856);
void live_h_12(double *state, double *unused, double *out_5943370320285196750);
void live_H_12(double *state, double *unused, double *out_3786872978053889805);
void live_h_35(double *state, double *unused, double *out_6309170454331704755);
void live_H_35(double *state, double *unused, double *out_6532436010378903514);
void live_h_32(double *state, double *unused, double *out_712856769424299987);
void live_H_32(double *state, double *unused, double *out_6113003691123035544);
void live_h_13(double *state, double *unused, double *out_3295619973503022245);
void live_H_13(double *state, double *unused, double *out_3227789409205695008);
void live_h_14(double *state, double *unused, double *out_7515695079624580786);
void live_H_14(double *state, double *unused, double *out_991393783348481345);
void live_h_33(double *state, double *unused, double *out_9154808789490814140);
void live_H_33(double *state, double *unused, double *out_5284635632033392990);
void live_predict(double *in_x, double *in_P, double *in_Q, double dt);
}