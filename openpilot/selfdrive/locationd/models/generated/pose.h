#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_err_fun(double *nom_x, double *delta_x, double *out_7519798370927896678);
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_7487201815754910304);
void pose_H_mod_fun(double *state, double *out_1163177465718205104);
void pose_f_fun(double *state, double dt, double *out_3990854090903749199);
void pose_F_fun(double *state, double dt, double *out_1836760290158182993);
void pose_h_4(double *state, double *unused, double *out_2491156385417327206);
void pose_H_4(double *state, double *unused, double *out_7781184200339616238);
void pose_h_10(double *state, double *unused, double *out_935983163405023118);
void pose_H_10(double *state, double *unused, double *out_250545266026384824);
void pose_h_13(double *state, double *unused, double *out_2877352012270184476);
void pose_H_13(double *state, double *unused, double *out_4568910375007283437);
void pose_h_14(double *state, double *unused, double *out_5876458652377630242);
void pose_H_14(double *state, double *unused, double *out_3817943344000131709);
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt);
}