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
void live_H(double *in_vec, double *out_3838508326029222336);
void live_err_fun(double *nom_x, double *delta_x, double *out_4667420866813392492);
void live_inv_err_fun(double *nom_x, double *true_x, double *out_4965089596984406727);
void live_H_mod_fun(double *state, double *out_375055522917579266);
void live_f_fun(double *state, double dt, double *out_5098222361971347778);
void live_F_fun(double *state, double dt, double *out_5653568815684921221);
void live_h_4(double *state, double *unused, double *out_5950988231722169027);
void live_H_4(double *state, double *unused, double *out_9132330737447647805);
void live_h_9(double *state, double *unused, double *out_5828868612411126408);
void live_H_9(double *state, double *unused, double *out_8891141090818057160);
void live_h_10(double *state, double *unused, double *out_5846814678830883123);
void live_H_10(double *state, double *unused, double *out_6676860114727357661);
void live_h_12(double *state, double *unused, double *out_3966605901215017760);
void live_H_12(double *state, double *unused, double *out_4112874329415686010);
void live_h_35(double *state, double *unused, double *out_1928605790376079113);
void live_H_35(double *state, double *unused, double *out_5765668680075040429);
void live_h_32(double *state, double *unused, double *out_8725343659216170708);
void live_H_32(double *state, double *unused, double *out_7410508189785940031);
void live_h_13(double *state, double *unused, double *out_1416649593870749999);
void live_H_13(double *state, double *unused, double *out_2171338643311421728);
void live_h_14(double *state, double *unused, double *out_5828868612411126408);
void live_H_14(double *state, double *unused, double *out_8891141090818057160);
void live_h_33(double *state, double *unused, double *out_6825849965520087263);
void live_H_33(double *state, double *unused, double *out_2615111675436182825);
void live_predict(double *in_x, double *in_P, double *in_Q, double dt);
}