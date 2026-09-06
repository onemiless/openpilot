#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_err_fun(double *nom_x, double *delta_x, double *out_8898640593533968832);
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_3435172889934915688);
void pose_H_mod_fun(double *state, double *out_8426427664152767868);
void pose_f_fun(double *state, double dt, double *out_4211470879648912048);
void pose_F_fun(double *state, double dt, double *out_6812913047568660000);
void pose_h_4(double *state, double *unused, double *out_6777878803091675943);
void pose_H_4(double *state, double *unused, double *out_3322402639485405722);
void pose_h_10(double *state, double *unused, double *out_7706867558898837591);
void pose_H_10(double *state, double *unused, double *out_1882782654140805881);
void pose_h_13(double *state, double *unused, double *out_7433113681699853348);
void pose_H_13(double *state, double *unused, double *out_4288228568831295207);
void pose_h_14(double *state, double *unused, double *out_7770713869499660906);
void pose_H_14(double *state, double *unused, double *out_6405191071780778018);
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt);
}