#include "pose.h"

namespace {
#define DIM 18
#define EDIM 18
#define MEDIM 18
typedef void (*Hfun)(double *, double *, double *);
const static double MAHA_THRESH_4 = 7.814727903251177;
const static double MAHA_THRESH_10 = 7.814727903251177;
const static double MAHA_THRESH_13 = 7.814727903251177;
const static double MAHA_THRESH_14 = 7.814727903251177;

/******************************************************************************
 *                      Code generated with SymPy 1.14.0                      *
 *                                                                            *
 *              See http://www.sympy.org/ for more information.               *
 *                                                                            *
 *                         This file is part of 'ekf'                         *
 ******************************************************************************/
void err_fun(double *nom_x, double *delta_x, double *out_7519798370927896678) {
   out_7519798370927896678[0] = delta_x[0] + nom_x[0];
   out_7519798370927896678[1] = delta_x[1] + nom_x[1];
   out_7519798370927896678[2] = delta_x[2] + nom_x[2];
   out_7519798370927896678[3] = delta_x[3] + nom_x[3];
   out_7519798370927896678[4] = delta_x[4] + nom_x[4];
   out_7519798370927896678[5] = delta_x[5] + nom_x[5];
   out_7519798370927896678[6] = delta_x[6] + nom_x[6];
   out_7519798370927896678[7] = delta_x[7] + nom_x[7];
   out_7519798370927896678[8] = delta_x[8] + nom_x[8];
   out_7519798370927896678[9] = delta_x[9] + nom_x[9];
   out_7519798370927896678[10] = delta_x[10] + nom_x[10];
   out_7519798370927896678[11] = delta_x[11] + nom_x[11];
   out_7519798370927896678[12] = delta_x[12] + nom_x[12];
   out_7519798370927896678[13] = delta_x[13] + nom_x[13];
   out_7519798370927896678[14] = delta_x[14] + nom_x[14];
   out_7519798370927896678[15] = delta_x[15] + nom_x[15];
   out_7519798370927896678[16] = delta_x[16] + nom_x[16];
   out_7519798370927896678[17] = delta_x[17] + nom_x[17];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_7487201815754910304) {
   out_7487201815754910304[0] = -nom_x[0] + true_x[0];
   out_7487201815754910304[1] = -nom_x[1] + true_x[1];
   out_7487201815754910304[2] = -nom_x[2] + true_x[2];
   out_7487201815754910304[3] = -nom_x[3] + true_x[3];
   out_7487201815754910304[4] = -nom_x[4] + true_x[4];
   out_7487201815754910304[5] = -nom_x[5] + true_x[5];
   out_7487201815754910304[6] = -nom_x[6] + true_x[6];
   out_7487201815754910304[7] = -nom_x[7] + true_x[7];
   out_7487201815754910304[8] = -nom_x[8] + true_x[8];
   out_7487201815754910304[9] = -nom_x[9] + true_x[9];
   out_7487201815754910304[10] = -nom_x[10] + true_x[10];
   out_7487201815754910304[11] = -nom_x[11] + true_x[11];
   out_7487201815754910304[12] = -nom_x[12] + true_x[12];
   out_7487201815754910304[13] = -nom_x[13] + true_x[13];
   out_7487201815754910304[14] = -nom_x[14] + true_x[14];
   out_7487201815754910304[15] = -nom_x[15] + true_x[15];
   out_7487201815754910304[16] = -nom_x[16] + true_x[16];
   out_7487201815754910304[17] = -nom_x[17] + true_x[17];
}
void H_mod_fun(double *state, double *out_1163177465718205104) {
   out_1163177465718205104[0] = 1.0;
   out_1163177465718205104[1] = 0.0;
   out_1163177465718205104[2] = 0.0;
   out_1163177465718205104[3] = 0.0;
   out_1163177465718205104[4] = 0.0;
   out_1163177465718205104[5] = 0.0;
   out_1163177465718205104[6] = 0.0;
   out_1163177465718205104[7] = 0.0;
   out_1163177465718205104[8] = 0.0;
   out_1163177465718205104[9] = 0.0;
   out_1163177465718205104[10] = 0.0;
   out_1163177465718205104[11] = 0.0;
   out_1163177465718205104[12] = 0.0;
   out_1163177465718205104[13] = 0.0;
   out_1163177465718205104[14] = 0.0;
   out_1163177465718205104[15] = 0.0;
   out_1163177465718205104[16] = 0.0;
   out_1163177465718205104[17] = 0.0;
   out_1163177465718205104[18] = 0.0;
   out_1163177465718205104[19] = 1.0;
   out_1163177465718205104[20] = 0.0;
   out_1163177465718205104[21] = 0.0;
   out_1163177465718205104[22] = 0.0;
   out_1163177465718205104[23] = 0.0;
   out_1163177465718205104[24] = 0.0;
   out_1163177465718205104[25] = 0.0;
   out_1163177465718205104[26] = 0.0;
   out_1163177465718205104[27] = 0.0;
   out_1163177465718205104[28] = 0.0;
   out_1163177465718205104[29] = 0.0;
   out_1163177465718205104[30] = 0.0;
   out_1163177465718205104[31] = 0.0;
   out_1163177465718205104[32] = 0.0;
   out_1163177465718205104[33] = 0.0;
   out_1163177465718205104[34] = 0.0;
   out_1163177465718205104[35] = 0.0;
   out_1163177465718205104[36] = 0.0;
   out_1163177465718205104[37] = 0.0;
   out_1163177465718205104[38] = 1.0;
   out_1163177465718205104[39] = 0.0;
   out_1163177465718205104[40] = 0.0;
   out_1163177465718205104[41] = 0.0;
   out_1163177465718205104[42] = 0.0;
   out_1163177465718205104[43] = 0.0;
   out_1163177465718205104[44] = 0.0;
   out_1163177465718205104[45] = 0.0;
   out_1163177465718205104[46] = 0.0;
   out_1163177465718205104[47] = 0.0;
   out_1163177465718205104[48] = 0.0;
   out_1163177465718205104[49] = 0.0;
   out_1163177465718205104[50] = 0.0;
   out_1163177465718205104[51] = 0.0;
   out_1163177465718205104[52] = 0.0;
   out_1163177465718205104[53] = 0.0;
   out_1163177465718205104[54] = 0.0;
   out_1163177465718205104[55] = 0.0;
   out_1163177465718205104[56] = 0.0;
   out_1163177465718205104[57] = 1.0;
   out_1163177465718205104[58] = 0.0;
   out_1163177465718205104[59] = 0.0;
   out_1163177465718205104[60] = 0.0;
   out_1163177465718205104[61] = 0.0;
   out_1163177465718205104[62] = 0.0;
   out_1163177465718205104[63] = 0.0;
   out_1163177465718205104[64] = 0.0;
   out_1163177465718205104[65] = 0.0;
   out_1163177465718205104[66] = 0.0;
   out_1163177465718205104[67] = 0.0;
   out_1163177465718205104[68] = 0.0;
   out_1163177465718205104[69] = 0.0;
   out_1163177465718205104[70] = 0.0;
   out_1163177465718205104[71] = 0.0;
   out_1163177465718205104[72] = 0.0;
   out_1163177465718205104[73] = 0.0;
   out_1163177465718205104[74] = 0.0;
   out_1163177465718205104[75] = 0.0;
   out_1163177465718205104[76] = 1.0;
   out_1163177465718205104[77] = 0.0;
   out_1163177465718205104[78] = 0.0;
   out_1163177465718205104[79] = 0.0;
   out_1163177465718205104[80] = 0.0;
   out_1163177465718205104[81] = 0.0;
   out_1163177465718205104[82] = 0.0;
   out_1163177465718205104[83] = 0.0;
   out_1163177465718205104[84] = 0.0;
   out_1163177465718205104[85] = 0.0;
   out_1163177465718205104[86] = 0.0;
   out_1163177465718205104[87] = 0.0;
   out_1163177465718205104[88] = 0.0;
   out_1163177465718205104[89] = 0.0;
   out_1163177465718205104[90] = 0.0;
   out_1163177465718205104[91] = 0.0;
   out_1163177465718205104[92] = 0.0;
   out_1163177465718205104[93] = 0.0;
   out_1163177465718205104[94] = 0.0;
   out_1163177465718205104[95] = 1.0;
   out_1163177465718205104[96] = 0.0;
   out_1163177465718205104[97] = 0.0;
   out_1163177465718205104[98] = 0.0;
   out_1163177465718205104[99] = 0.0;
   out_1163177465718205104[100] = 0.0;
   out_1163177465718205104[101] = 0.0;
   out_1163177465718205104[102] = 0.0;
   out_1163177465718205104[103] = 0.0;
   out_1163177465718205104[104] = 0.0;
   out_1163177465718205104[105] = 0.0;
   out_1163177465718205104[106] = 0.0;
   out_1163177465718205104[107] = 0.0;
   out_1163177465718205104[108] = 0.0;
   out_1163177465718205104[109] = 0.0;
   out_1163177465718205104[110] = 0.0;
   out_1163177465718205104[111] = 0.0;
   out_1163177465718205104[112] = 0.0;
   out_1163177465718205104[113] = 0.0;
   out_1163177465718205104[114] = 1.0;
   out_1163177465718205104[115] = 0.0;
   out_1163177465718205104[116] = 0.0;
   out_1163177465718205104[117] = 0.0;
   out_1163177465718205104[118] = 0.0;
   out_1163177465718205104[119] = 0.0;
   out_1163177465718205104[120] = 0.0;
   out_1163177465718205104[121] = 0.0;
   out_1163177465718205104[122] = 0.0;
   out_1163177465718205104[123] = 0.0;
   out_1163177465718205104[124] = 0.0;
   out_1163177465718205104[125] = 0.0;
   out_1163177465718205104[126] = 0.0;
   out_1163177465718205104[127] = 0.0;
   out_1163177465718205104[128] = 0.0;
   out_1163177465718205104[129] = 0.0;
   out_1163177465718205104[130] = 0.0;
   out_1163177465718205104[131] = 0.0;
   out_1163177465718205104[132] = 0.0;
   out_1163177465718205104[133] = 1.0;
   out_1163177465718205104[134] = 0.0;
   out_1163177465718205104[135] = 0.0;
   out_1163177465718205104[136] = 0.0;
   out_1163177465718205104[137] = 0.0;
   out_1163177465718205104[138] = 0.0;
   out_1163177465718205104[139] = 0.0;
   out_1163177465718205104[140] = 0.0;
   out_1163177465718205104[141] = 0.0;
   out_1163177465718205104[142] = 0.0;
   out_1163177465718205104[143] = 0.0;
   out_1163177465718205104[144] = 0.0;
   out_1163177465718205104[145] = 0.0;
   out_1163177465718205104[146] = 0.0;
   out_1163177465718205104[147] = 0.0;
   out_1163177465718205104[148] = 0.0;
   out_1163177465718205104[149] = 0.0;
   out_1163177465718205104[150] = 0.0;
   out_1163177465718205104[151] = 0.0;
   out_1163177465718205104[152] = 1.0;
   out_1163177465718205104[153] = 0.0;
   out_1163177465718205104[154] = 0.0;
   out_1163177465718205104[155] = 0.0;
   out_1163177465718205104[156] = 0.0;
   out_1163177465718205104[157] = 0.0;
   out_1163177465718205104[158] = 0.0;
   out_1163177465718205104[159] = 0.0;
   out_1163177465718205104[160] = 0.0;
   out_1163177465718205104[161] = 0.0;
   out_1163177465718205104[162] = 0.0;
   out_1163177465718205104[163] = 0.0;
   out_1163177465718205104[164] = 0.0;
   out_1163177465718205104[165] = 0.0;
   out_1163177465718205104[166] = 0.0;
   out_1163177465718205104[167] = 0.0;
   out_1163177465718205104[168] = 0.0;
   out_1163177465718205104[169] = 0.0;
   out_1163177465718205104[170] = 0.0;
   out_1163177465718205104[171] = 1.0;
   out_1163177465718205104[172] = 0.0;
   out_1163177465718205104[173] = 0.0;
   out_1163177465718205104[174] = 0.0;
   out_1163177465718205104[175] = 0.0;
   out_1163177465718205104[176] = 0.0;
   out_1163177465718205104[177] = 0.0;
   out_1163177465718205104[178] = 0.0;
   out_1163177465718205104[179] = 0.0;
   out_1163177465718205104[180] = 0.0;
   out_1163177465718205104[181] = 0.0;
   out_1163177465718205104[182] = 0.0;
   out_1163177465718205104[183] = 0.0;
   out_1163177465718205104[184] = 0.0;
   out_1163177465718205104[185] = 0.0;
   out_1163177465718205104[186] = 0.0;
   out_1163177465718205104[187] = 0.0;
   out_1163177465718205104[188] = 0.0;
   out_1163177465718205104[189] = 0.0;
   out_1163177465718205104[190] = 1.0;
   out_1163177465718205104[191] = 0.0;
   out_1163177465718205104[192] = 0.0;
   out_1163177465718205104[193] = 0.0;
   out_1163177465718205104[194] = 0.0;
   out_1163177465718205104[195] = 0.0;
   out_1163177465718205104[196] = 0.0;
   out_1163177465718205104[197] = 0.0;
   out_1163177465718205104[198] = 0.0;
   out_1163177465718205104[199] = 0.0;
   out_1163177465718205104[200] = 0.0;
   out_1163177465718205104[201] = 0.0;
   out_1163177465718205104[202] = 0.0;
   out_1163177465718205104[203] = 0.0;
   out_1163177465718205104[204] = 0.0;
   out_1163177465718205104[205] = 0.0;
   out_1163177465718205104[206] = 0.0;
   out_1163177465718205104[207] = 0.0;
   out_1163177465718205104[208] = 0.0;
   out_1163177465718205104[209] = 1.0;
   out_1163177465718205104[210] = 0.0;
   out_1163177465718205104[211] = 0.0;
   out_1163177465718205104[212] = 0.0;
   out_1163177465718205104[213] = 0.0;
   out_1163177465718205104[214] = 0.0;
   out_1163177465718205104[215] = 0.0;
   out_1163177465718205104[216] = 0.0;
   out_1163177465718205104[217] = 0.0;
   out_1163177465718205104[218] = 0.0;
   out_1163177465718205104[219] = 0.0;
   out_1163177465718205104[220] = 0.0;
   out_1163177465718205104[221] = 0.0;
   out_1163177465718205104[222] = 0.0;
   out_1163177465718205104[223] = 0.0;
   out_1163177465718205104[224] = 0.0;
   out_1163177465718205104[225] = 0.0;
   out_1163177465718205104[226] = 0.0;
   out_1163177465718205104[227] = 0.0;
   out_1163177465718205104[228] = 1.0;
   out_1163177465718205104[229] = 0.0;
   out_1163177465718205104[230] = 0.0;
   out_1163177465718205104[231] = 0.0;
   out_1163177465718205104[232] = 0.0;
   out_1163177465718205104[233] = 0.0;
   out_1163177465718205104[234] = 0.0;
   out_1163177465718205104[235] = 0.0;
   out_1163177465718205104[236] = 0.0;
   out_1163177465718205104[237] = 0.0;
   out_1163177465718205104[238] = 0.0;
   out_1163177465718205104[239] = 0.0;
   out_1163177465718205104[240] = 0.0;
   out_1163177465718205104[241] = 0.0;
   out_1163177465718205104[242] = 0.0;
   out_1163177465718205104[243] = 0.0;
   out_1163177465718205104[244] = 0.0;
   out_1163177465718205104[245] = 0.0;
   out_1163177465718205104[246] = 0.0;
   out_1163177465718205104[247] = 1.0;
   out_1163177465718205104[248] = 0.0;
   out_1163177465718205104[249] = 0.0;
   out_1163177465718205104[250] = 0.0;
   out_1163177465718205104[251] = 0.0;
   out_1163177465718205104[252] = 0.0;
   out_1163177465718205104[253] = 0.0;
   out_1163177465718205104[254] = 0.0;
   out_1163177465718205104[255] = 0.0;
   out_1163177465718205104[256] = 0.0;
   out_1163177465718205104[257] = 0.0;
   out_1163177465718205104[258] = 0.0;
   out_1163177465718205104[259] = 0.0;
   out_1163177465718205104[260] = 0.0;
   out_1163177465718205104[261] = 0.0;
   out_1163177465718205104[262] = 0.0;
   out_1163177465718205104[263] = 0.0;
   out_1163177465718205104[264] = 0.0;
   out_1163177465718205104[265] = 0.0;
   out_1163177465718205104[266] = 1.0;
   out_1163177465718205104[267] = 0.0;
   out_1163177465718205104[268] = 0.0;
   out_1163177465718205104[269] = 0.0;
   out_1163177465718205104[270] = 0.0;
   out_1163177465718205104[271] = 0.0;
   out_1163177465718205104[272] = 0.0;
   out_1163177465718205104[273] = 0.0;
   out_1163177465718205104[274] = 0.0;
   out_1163177465718205104[275] = 0.0;
   out_1163177465718205104[276] = 0.0;
   out_1163177465718205104[277] = 0.0;
   out_1163177465718205104[278] = 0.0;
   out_1163177465718205104[279] = 0.0;
   out_1163177465718205104[280] = 0.0;
   out_1163177465718205104[281] = 0.0;
   out_1163177465718205104[282] = 0.0;
   out_1163177465718205104[283] = 0.0;
   out_1163177465718205104[284] = 0.0;
   out_1163177465718205104[285] = 1.0;
   out_1163177465718205104[286] = 0.0;
   out_1163177465718205104[287] = 0.0;
   out_1163177465718205104[288] = 0.0;
   out_1163177465718205104[289] = 0.0;
   out_1163177465718205104[290] = 0.0;
   out_1163177465718205104[291] = 0.0;
   out_1163177465718205104[292] = 0.0;
   out_1163177465718205104[293] = 0.0;
   out_1163177465718205104[294] = 0.0;
   out_1163177465718205104[295] = 0.0;
   out_1163177465718205104[296] = 0.0;
   out_1163177465718205104[297] = 0.0;
   out_1163177465718205104[298] = 0.0;
   out_1163177465718205104[299] = 0.0;
   out_1163177465718205104[300] = 0.0;
   out_1163177465718205104[301] = 0.0;
   out_1163177465718205104[302] = 0.0;
   out_1163177465718205104[303] = 0.0;
   out_1163177465718205104[304] = 1.0;
   out_1163177465718205104[305] = 0.0;
   out_1163177465718205104[306] = 0.0;
   out_1163177465718205104[307] = 0.0;
   out_1163177465718205104[308] = 0.0;
   out_1163177465718205104[309] = 0.0;
   out_1163177465718205104[310] = 0.0;
   out_1163177465718205104[311] = 0.0;
   out_1163177465718205104[312] = 0.0;
   out_1163177465718205104[313] = 0.0;
   out_1163177465718205104[314] = 0.0;
   out_1163177465718205104[315] = 0.0;
   out_1163177465718205104[316] = 0.0;
   out_1163177465718205104[317] = 0.0;
   out_1163177465718205104[318] = 0.0;
   out_1163177465718205104[319] = 0.0;
   out_1163177465718205104[320] = 0.0;
   out_1163177465718205104[321] = 0.0;
   out_1163177465718205104[322] = 0.0;
   out_1163177465718205104[323] = 1.0;
}
void f_fun(double *state, double dt, double *out_3990854090903749199) {
   out_3990854090903749199[0] = atan2((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), -(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]));
   out_3990854090903749199[1] = asin(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]));
   out_3990854090903749199[2] = atan2(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), -(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]));
   out_3990854090903749199[3] = dt*state[12] + state[3];
   out_3990854090903749199[4] = dt*state[13] + state[4];
   out_3990854090903749199[5] = dt*state[14] + state[5];
   out_3990854090903749199[6] = state[6];
   out_3990854090903749199[7] = state[7];
   out_3990854090903749199[8] = state[8];
   out_3990854090903749199[9] = state[9];
   out_3990854090903749199[10] = state[10];
   out_3990854090903749199[11] = state[11];
   out_3990854090903749199[12] = state[12];
   out_3990854090903749199[13] = state[13];
   out_3990854090903749199[14] = state[14];
   out_3990854090903749199[15] = state[15];
   out_3990854090903749199[16] = state[16];
   out_3990854090903749199[17] = state[17];
}
void F_fun(double *state, double dt, double *out_1836760290158182993) {
   out_1836760290158182993[0] = ((-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*cos(state[0])*cos(state[1]) - sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*cos(state[0])*cos(state[1]) - sin(dt*state[6])*sin(state[0])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_1836760290158182993[1] = ((-sin(dt*state[6])*sin(dt*state[8]) - sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*cos(state[1]) - (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*sin(state[1]) - sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(state[0]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*sin(state[1]) + (-sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) + sin(dt*state[8])*cos(dt*state[6]))*cos(state[1]) - sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(state[0]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_1836760290158182993[2] = 0;
   out_1836760290158182993[3] = 0;
   out_1836760290158182993[4] = 0;
   out_1836760290158182993[5] = 0;
   out_1836760290158182993[6] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(dt*cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) - dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_1836760290158182993[7] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*sin(dt*state[7])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[6])*sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) - dt*sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[7])*cos(dt*state[6])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[8])*sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]) - dt*sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_1836760290158182993[8] = ((dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((dt*sin(dt*state[6])*sin(dt*state[8]) + dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_1836760290158182993[9] = 0;
   out_1836760290158182993[10] = 0;
   out_1836760290158182993[11] = 0;
   out_1836760290158182993[12] = 0;
   out_1836760290158182993[13] = 0;
   out_1836760290158182993[14] = 0;
   out_1836760290158182993[15] = 0;
   out_1836760290158182993[16] = 0;
   out_1836760290158182993[17] = 0;
   out_1836760290158182993[18] = (-sin(dt*state[7])*sin(state[0])*cos(state[1]) - sin(dt*state[8])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_1836760290158182993[19] = (-sin(dt*state[7])*sin(state[1])*cos(state[0]) + sin(dt*state[8])*sin(state[0])*sin(state[1])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_1836760290158182993[20] = 0;
   out_1836760290158182993[21] = 0;
   out_1836760290158182993[22] = 0;
   out_1836760290158182993[23] = 0;
   out_1836760290158182993[24] = 0;
   out_1836760290158182993[25] = (dt*sin(dt*state[7])*sin(dt*state[8])*sin(state[0])*cos(state[1]) - dt*sin(dt*state[7])*sin(state[1])*cos(dt*state[8]) + dt*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_1836760290158182993[26] = (-dt*sin(dt*state[8])*sin(state[1])*cos(dt*state[7]) - dt*sin(state[0])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_1836760290158182993[27] = 0;
   out_1836760290158182993[28] = 0;
   out_1836760290158182993[29] = 0;
   out_1836760290158182993[30] = 0;
   out_1836760290158182993[31] = 0;
   out_1836760290158182993[32] = 0;
   out_1836760290158182993[33] = 0;
   out_1836760290158182993[34] = 0;
   out_1836760290158182993[35] = 0;
   out_1836760290158182993[36] = ((sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_1836760290158182993[37] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-sin(dt*state[7])*sin(state[2])*cos(state[0])*cos(state[1]) + sin(dt*state[8])*sin(state[0])*sin(state[2])*cos(dt*state[7])*cos(state[1]) - sin(state[1])*sin(state[2])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(-sin(dt*state[7])*cos(state[0])*cos(state[1])*cos(state[2]) + sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1])*cos(state[2]) - sin(state[1])*cos(dt*state[7])*cos(dt*state[8])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_1836760290158182993[38] = ((-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (-sin(state[0])*sin(state[1])*sin(state[2]) - cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_1836760290158182993[39] = 0;
   out_1836760290158182993[40] = 0;
   out_1836760290158182993[41] = 0;
   out_1836760290158182993[42] = 0;
   out_1836760290158182993[43] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(dt*(sin(state[0])*cos(state[2]) - sin(state[1])*sin(state[2])*cos(state[0]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*sin(state[2])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(dt*(-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_1836760290158182993[44] = (dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*sin(state[2])*cos(dt*state[7])*cos(state[1]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + (dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[7])*cos(state[1])*cos(state[2]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_1836760290158182993[45] = 0;
   out_1836760290158182993[46] = 0;
   out_1836760290158182993[47] = 0;
   out_1836760290158182993[48] = 0;
   out_1836760290158182993[49] = 0;
   out_1836760290158182993[50] = 0;
   out_1836760290158182993[51] = 0;
   out_1836760290158182993[52] = 0;
   out_1836760290158182993[53] = 0;
   out_1836760290158182993[54] = 0;
   out_1836760290158182993[55] = 0;
   out_1836760290158182993[56] = 0;
   out_1836760290158182993[57] = 1;
   out_1836760290158182993[58] = 0;
   out_1836760290158182993[59] = 0;
   out_1836760290158182993[60] = 0;
   out_1836760290158182993[61] = 0;
   out_1836760290158182993[62] = 0;
   out_1836760290158182993[63] = 0;
   out_1836760290158182993[64] = 0;
   out_1836760290158182993[65] = 0;
   out_1836760290158182993[66] = dt;
   out_1836760290158182993[67] = 0;
   out_1836760290158182993[68] = 0;
   out_1836760290158182993[69] = 0;
   out_1836760290158182993[70] = 0;
   out_1836760290158182993[71] = 0;
   out_1836760290158182993[72] = 0;
   out_1836760290158182993[73] = 0;
   out_1836760290158182993[74] = 0;
   out_1836760290158182993[75] = 0;
   out_1836760290158182993[76] = 1;
   out_1836760290158182993[77] = 0;
   out_1836760290158182993[78] = 0;
   out_1836760290158182993[79] = 0;
   out_1836760290158182993[80] = 0;
   out_1836760290158182993[81] = 0;
   out_1836760290158182993[82] = 0;
   out_1836760290158182993[83] = 0;
   out_1836760290158182993[84] = 0;
   out_1836760290158182993[85] = dt;
   out_1836760290158182993[86] = 0;
   out_1836760290158182993[87] = 0;
   out_1836760290158182993[88] = 0;
   out_1836760290158182993[89] = 0;
   out_1836760290158182993[90] = 0;
   out_1836760290158182993[91] = 0;
   out_1836760290158182993[92] = 0;
   out_1836760290158182993[93] = 0;
   out_1836760290158182993[94] = 0;
   out_1836760290158182993[95] = 1;
   out_1836760290158182993[96] = 0;
   out_1836760290158182993[97] = 0;
   out_1836760290158182993[98] = 0;
   out_1836760290158182993[99] = 0;
   out_1836760290158182993[100] = 0;
   out_1836760290158182993[101] = 0;
   out_1836760290158182993[102] = 0;
   out_1836760290158182993[103] = 0;
   out_1836760290158182993[104] = dt;
   out_1836760290158182993[105] = 0;
   out_1836760290158182993[106] = 0;
   out_1836760290158182993[107] = 0;
   out_1836760290158182993[108] = 0;
   out_1836760290158182993[109] = 0;
   out_1836760290158182993[110] = 0;
   out_1836760290158182993[111] = 0;
   out_1836760290158182993[112] = 0;
   out_1836760290158182993[113] = 0;
   out_1836760290158182993[114] = 1;
   out_1836760290158182993[115] = 0;
   out_1836760290158182993[116] = 0;
   out_1836760290158182993[117] = 0;
   out_1836760290158182993[118] = 0;
   out_1836760290158182993[119] = 0;
   out_1836760290158182993[120] = 0;
   out_1836760290158182993[121] = 0;
   out_1836760290158182993[122] = 0;
   out_1836760290158182993[123] = 0;
   out_1836760290158182993[124] = 0;
   out_1836760290158182993[125] = 0;
   out_1836760290158182993[126] = 0;
   out_1836760290158182993[127] = 0;
   out_1836760290158182993[128] = 0;
   out_1836760290158182993[129] = 0;
   out_1836760290158182993[130] = 0;
   out_1836760290158182993[131] = 0;
   out_1836760290158182993[132] = 0;
   out_1836760290158182993[133] = 1;
   out_1836760290158182993[134] = 0;
   out_1836760290158182993[135] = 0;
   out_1836760290158182993[136] = 0;
   out_1836760290158182993[137] = 0;
   out_1836760290158182993[138] = 0;
   out_1836760290158182993[139] = 0;
   out_1836760290158182993[140] = 0;
   out_1836760290158182993[141] = 0;
   out_1836760290158182993[142] = 0;
   out_1836760290158182993[143] = 0;
   out_1836760290158182993[144] = 0;
   out_1836760290158182993[145] = 0;
   out_1836760290158182993[146] = 0;
   out_1836760290158182993[147] = 0;
   out_1836760290158182993[148] = 0;
   out_1836760290158182993[149] = 0;
   out_1836760290158182993[150] = 0;
   out_1836760290158182993[151] = 0;
   out_1836760290158182993[152] = 1;
   out_1836760290158182993[153] = 0;
   out_1836760290158182993[154] = 0;
   out_1836760290158182993[155] = 0;
   out_1836760290158182993[156] = 0;
   out_1836760290158182993[157] = 0;
   out_1836760290158182993[158] = 0;
   out_1836760290158182993[159] = 0;
   out_1836760290158182993[160] = 0;
   out_1836760290158182993[161] = 0;
   out_1836760290158182993[162] = 0;
   out_1836760290158182993[163] = 0;
   out_1836760290158182993[164] = 0;
   out_1836760290158182993[165] = 0;
   out_1836760290158182993[166] = 0;
   out_1836760290158182993[167] = 0;
   out_1836760290158182993[168] = 0;
   out_1836760290158182993[169] = 0;
   out_1836760290158182993[170] = 0;
   out_1836760290158182993[171] = 1;
   out_1836760290158182993[172] = 0;
   out_1836760290158182993[173] = 0;
   out_1836760290158182993[174] = 0;
   out_1836760290158182993[175] = 0;
   out_1836760290158182993[176] = 0;
   out_1836760290158182993[177] = 0;
   out_1836760290158182993[178] = 0;
   out_1836760290158182993[179] = 0;
   out_1836760290158182993[180] = 0;
   out_1836760290158182993[181] = 0;
   out_1836760290158182993[182] = 0;
   out_1836760290158182993[183] = 0;
   out_1836760290158182993[184] = 0;
   out_1836760290158182993[185] = 0;
   out_1836760290158182993[186] = 0;
   out_1836760290158182993[187] = 0;
   out_1836760290158182993[188] = 0;
   out_1836760290158182993[189] = 0;
   out_1836760290158182993[190] = 1;
   out_1836760290158182993[191] = 0;
   out_1836760290158182993[192] = 0;
   out_1836760290158182993[193] = 0;
   out_1836760290158182993[194] = 0;
   out_1836760290158182993[195] = 0;
   out_1836760290158182993[196] = 0;
   out_1836760290158182993[197] = 0;
   out_1836760290158182993[198] = 0;
   out_1836760290158182993[199] = 0;
   out_1836760290158182993[200] = 0;
   out_1836760290158182993[201] = 0;
   out_1836760290158182993[202] = 0;
   out_1836760290158182993[203] = 0;
   out_1836760290158182993[204] = 0;
   out_1836760290158182993[205] = 0;
   out_1836760290158182993[206] = 0;
   out_1836760290158182993[207] = 0;
   out_1836760290158182993[208] = 0;
   out_1836760290158182993[209] = 1;
   out_1836760290158182993[210] = 0;
   out_1836760290158182993[211] = 0;
   out_1836760290158182993[212] = 0;
   out_1836760290158182993[213] = 0;
   out_1836760290158182993[214] = 0;
   out_1836760290158182993[215] = 0;
   out_1836760290158182993[216] = 0;
   out_1836760290158182993[217] = 0;
   out_1836760290158182993[218] = 0;
   out_1836760290158182993[219] = 0;
   out_1836760290158182993[220] = 0;
   out_1836760290158182993[221] = 0;
   out_1836760290158182993[222] = 0;
   out_1836760290158182993[223] = 0;
   out_1836760290158182993[224] = 0;
   out_1836760290158182993[225] = 0;
   out_1836760290158182993[226] = 0;
   out_1836760290158182993[227] = 0;
   out_1836760290158182993[228] = 1;
   out_1836760290158182993[229] = 0;
   out_1836760290158182993[230] = 0;
   out_1836760290158182993[231] = 0;
   out_1836760290158182993[232] = 0;
   out_1836760290158182993[233] = 0;
   out_1836760290158182993[234] = 0;
   out_1836760290158182993[235] = 0;
   out_1836760290158182993[236] = 0;
   out_1836760290158182993[237] = 0;
   out_1836760290158182993[238] = 0;
   out_1836760290158182993[239] = 0;
   out_1836760290158182993[240] = 0;
   out_1836760290158182993[241] = 0;
   out_1836760290158182993[242] = 0;
   out_1836760290158182993[243] = 0;
   out_1836760290158182993[244] = 0;
   out_1836760290158182993[245] = 0;
   out_1836760290158182993[246] = 0;
   out_1836760290158182993[247] = 1;
   out_1836760290158182993[248] = 0;
   out_1836760290158182993[249] = 0;
   out_1836760290158182993[250] = 0;
   out_1836760290158182993[251] = 0;
   out_1836760290158182993[252] = 0;
   out_1836760290158182993[253] = 0;
   out_1836760290158182993[254] = 0;
   out_1836760290158182993[255] = 0;
   out_1836760290158182993[256] = 0;
   out_1836760290158182993[257] = 0;
   out_1836760290158182993[258] = 0;
   out_1836760290158182993[259] = 0;
   out_1836760290158182993[260] = 0;
   out_1836760290158182993[261] = 0;
   out_1836760290158182993[262] = 0;
   out_1836760290158182993[263] = 0;
   out_1836760290158182993[264] = 0;
   out_1836760290158182993[265] = 0;
   out_1836760290158182993[266] = 1;
   out_1836760290158182993[267] = 0;
   out_1836760290158182993[268] = 0;
   out_1836760290158182993[269] = 0;
   out_1836760290158182993[270] = 0;
   out_1836760290158182993[271] = 0;
   out_1836760290158182993[272] = 0;
   out_1836760290158182993[273] = 0;
   out_1836760290158182993[274] = 0;
   out_1836760290158182993[275] = 0;
   out_1836760290158182993[276] = 0;
   out_1836760290158182993[277] = 0;
   out_1836760290158182993[278] = 0;
   out_1836760290158182993[279] = 0;
   out_1836760290158182993[280] = 0;
   out_1836760290158182993[281] = 0;
   out_1836760290158182993[282] = 0;
   out_1836760290158182993[283] = 0;
   out_1836760290158182993[284] = 0;
   out_1836760290158182993[285] = 1;
   out_1836760290158182993[286] = 0;
   out_1836760290158182993[287] = 0;
   out_1836760290158182993[288] = 0;
   out_1836760290158182993[289] = 0;
   out_1836760290158182993[290] = 0;
   out_1836760290158182993[291] = 0;
   out_1836760290158182993[292] = 0;
   out_1836760290158182993[293] = 0;
   out_1836760290158182993[294] = 0;
   out_1836760290158182993[295] = 0;
   out_1836760290158182993[296] = 0;
   out_1836760290158182993[297] = 0;
   out_1836760290158182993[298] = 0;
   out_1836760290158182993[299] = 0;
   out_1836760290158182993[300] = 0;
   out_1836760290158182993[301] = 0;
   out_1836760290158182993[302] = 0;
   out_1836760290158182993[303] = 0;
   out_1836760290158182993[304] = 1;
   out_1836760290158182993[305] = 0;
   out_1836760290158182993[306] = 0;
   out_1836760290158182993[307] = 0;
   out_1836760290158182993[308] = 0;
   out_1836760290158182993[309] = 0;
   out_1836760290158182993[310] = 0;
   out_1836760290158182993[311] = 0;
   out_1836760290158182993[312] = 0;
   out_1836760290158182993[313] = 0;
   out_1836760290158182993[314] = 0;
   out_1836760290158182993[315] = 0;
   out_1836760290158182993[316] = 0;
   out_1836760290158182993[317] = 0;
   out_1836760290158182993[318] = 0;
   out_1836760290158182993[319] = 0;
   out_1836760290158182993[320] = 0;
   out_1836760290158182993[321] = 0;
   out_1836760290158182993[322] = 0;
   out_1836760290158182993[323] = 1;
}
void h_4(double *state, double *unused, double *out_2491156385417327206) {
   out_2491156385417327206[0] = state[6] + state[9];
   out_2491156385417327206[1] = state[7] + state[10];
   out_2491156385417327206[2] = state[8] + state[11];
}
void H_4(double *state, double *unused, double *out_7781184200339616238) {
   out_7781184200339616238[0] = 0;
   out_7781184200339616238[1] = 0;
   out_7781184200339616238[2] = 0;
   out_7781184200339616238[3] = 0;
   out_7781184200339616238[4] = 0;
   out_7781184200339616238[5] = 0;
   out_7781184200339616238[6] = 1;
   out_7781184200339616238[7] = 0;
   out_7781184200339616238[8] = 0;
   out_7781184200339616238[9] = 1;
   out_7781184200339616238[10] = 0;
   out_7781184200339616238[11] = 0;
   out_7781184200339616238[12] = 0;
   out_7781184200339616238[13] = 0;
   out_7781184200339616238[14] = 0;
   out_7781184200339616238[15] = 0;
   out_7781184200339616238[16] = 0;
   out_7781184200339616238[17] = 0;
   out_7781184200339616238[18] = 0;
   out_7781184200339616238[19] = 0;
   out_7781184200339616238[20] = 0;
   out_7781184200339616238[21] = 0;
   out_7781184200339616238[22] = 0;
   out_7781184200339616238[23] = 0;
   out_7781184200339616238[24] = 0;
   out_7781184200339616238[25] = 1;
   out_7781184200339616238[26] = 0;
   out_7781184200339616238[27] = 0;
   out_7781184200339616238[28] = 1;
   out_7781184200339616238[29] = 0;
   out_7781184200339616238[30] = 0;
   out_7781184200339616238[31] = 0;
   out_7781184200339616238[32] = 0;
   out_7781184200339616238[33] = 0;
   out_7781184200339616238[34] = 0;
   out_7781184200339616238[35] = 0;
   out_7781184200339616238[36] = 0;
   out_7781184200339616238[37] = 0;
   out_7781184200339616238[38] = 0;
   out_7781184200339616238[39] = 0;
   out_7781184200339616238[40] = 0;
   out_7781184200339616238[41] = 0;
   out_7781184200339616238[42] = 0;
   out_7781184200339616238[43] = 0;
   out_7781184200339616238[44] = 1;
   out_7781184200339616238[45] = 0;
   out_7781184200339616238[46] = 0;
   out_7781184200339616238[47] = 1;
   out_7781184200339616238[48] = 0;
   out_7781184200339616238[49] = 0;
   out_7781184200339616238[50] = 0;
   out_7781184200339616238[51] = 0;
   out_7781184200339616238[52] = 0;
   out_7781184200339616238[53] = 0;
}
void h_10(double *state, double *unused, double *out_935983163405023118) {
   out_935983163405023118[0] = 9.8100000000000005*sin(state[1]) - state[4]*state[8] + state[5]*state[7] + state[12] + state[15];
   out_935983163405023118[1] = -9.8100000000000005*sin(state[0])*cos(state[1]) + state[3]*state[8] - state[5]*state[6] + state[13] + state[16];
   out_935983163405023118[2] = -9.8100000000000005*cos(state[0])*cos(state[1]) - state[3]*state[7] + state[4]*state[6] + state[14] + state[17];
}
void H_10(double *state, double *unused, double *out_250545266026384824) {
   out_250545266026384824[0] = 0;
   out_250545266026384824[1] = 9.8100000000000005*cos(state[1]);
   out_250545266026384824[2] = 0;
   out_250545266026384824[3] = 0;
   out_250545266026384824[4] = -state[8];
   out_250545266026384824[5] = state[7];
   out_250545266026384824[6] = 0;
   out_250545266026384824[7] = state[5];
   out_250545266026384824[8] = -state[4];
   out_250545266026384824[9] = 0;
   out_250545266026384824[10] = 0;
   out_250545266026384824[11] = 0;
   out_250545266026384824[12] = 1;
   out_250545266026384824[13] = 0;
   out_250545266026384824[14] = 0;
   out_250545266026384824[15] = 1;
   out_250545266026384824[16] = 0;
   out_250545266026384824[17] = 0;
   out_250545266026384824[18] = -9.8100000000000005*cos(state[0])*cos(state[1]);
   out_250545266026384824[19] = 9.8100000000000005*sin(state[0])*sin(state[1]);
   out_250545266026384824[20] = 0;
   out_250545266026384824[21] = state[8];
   out_250545266026384824[22] = 0;
   out_250545266026384824[23] = -state[6];
   out_250545266026384824[24] = -state[5];
   out_250545266026384824[25] = 0;
   out_250545266026384824[26] = state[3];
   out_250545266026384824[27] = 0;
   out_250545266026384824[28] = 0;
   out_250545266026384824[29] = 0;
   out_250545266026384824[30] = 0;
   out_250545266026384824[31] = 1;
   out_250545266026384824[32] = 0;
   out_250545266026384824[33] = 0;
   out_250545266026384824[34] = 1;
   out_250545266026384824[35] = 0;
   out_250545266026384824[36] = 9.8100000000000005*sin(state[0])*cos(state[1]);
   out_250545266026384824[37] = 9.8100000000000005*sin(state[1])*cos(state[0]);
   out_250545266026384824[38] = 0;
   out_250545266026384824[39] = -state[7];
   out_250545266026384824[40] = state[6];
   out_250545266026384824[41] = 0;
   out_250545266026384824[42] = state[4];
   out_250545266026384824[43] = -state[3];
   out_250545266026384824[44] = 0;
   out_250545266026384824[45] = 0;
   out_250545266026384824[46] = 0;
   out_250545266026384824[47] = 0;
   out_250545266026384824[48] = 0;
   out_250545266026384824[49] = 0;
   out_250545266026384824[50] = 1;
   out_250545266026384824[51] = 0;
   out_250545266026384824[52] = 0;
   out_250545266026384824[53] = 1;
}
void h_13(double *state, double *unused, double *out_2877352012270184476) {
   out_2877352012270184476[0] = state[3];
   out_2877352012270184476[1] = state[4];
   out_2877352012270184476[2] = state[5];
}
void H_13(double *state, double *unused, double *out_4568910375007283437) {
   out_4568910375007283437[0] = 0;
   out_4568910375007283437[1] = 0;
   out_4568910375007283437[2] = 0;
   out_4568910375007283437[3] = 1;
   out_4568910375007283437[4] = 0;
   out_4568910375007283437[5] = 0;
   out_4568910375007283437[6] = 0;
   out_4568910375007283437[7] = 0;
   out_4568910375007283437[8] = 0;
   out_4568910375007283437[9] = 0;
   out_4568910375007283437[10] = 0;
   out_4568910375007283437[11] = 0;
   out_4568910375007283437[12] = 0;
   out_4568910375007283437[13] = 0;
   out_4568910375007283437[14] = 0;
   out_4568910375007283437[15] = 0;
   out_4568910375007283437[16] = 0;
   out_4568910375007283437[17] = 0;
   out_4568910375007283437[18] = 0;
   out_4568910375007283437[19] = 0;
   out_4568910375007283437[20] = 0;
   out_4568910375007283437[21] = 0;
   out_4568910375007283437[22] = 1;
   out_4568910375007283437[23] = 0;
   out_4568910375007283437[24] = 0;
   out_4568910375007283437[25] = 0;
   out_4568910375007283437[26] = 0;
   out_4568910375007283437[27] = 0;
   out_4568910375007283437[28] = 0;
   out_4568910375007283437[29] = 0;
   out_4568910375007283437[30] = 0;
   out_4568910375007283437[31] = 0;
   out_4568910375007283437[32] = 0;
   out_4568910375007283437[33] = 0;
   out_4568910375007283437[34] = 0;
   out_4568910375007283437[35] = 0;
   out_4568910375007283437[36] = 0;
   out_4568910375007283437[37] = 0;
   out_4568910375007283437[38] = 0;
   out_4568910375007283437[39] = 0;
   out_4568910375007283437[40] = 0;
   out_4568910375007283437[41] = 1;
   out_4568910375007283437[42] = 0;
   out_4568910375007283437[43] = 0;
   out_4568910375007283437[44] = 0;
   out_4568910375007283437[45] = 0;
   out_4568910375007283437[46] = 0;
   out_4568910375007283437[47] = 0;
   out_4568910375007283437[48] = 0;
   out_4568910375007283437[49] = 0;
   out_4568910375007283437[50] = 0;
   out_4568910375007283437[51] = 0;
   out_4568910375007283437[52] = 0;
   out_4568910375007283437[53] = 0;
}
void h_14(double *state, double *unused, double *out_5876458652377630242) {
   out_5876458652377630242[0] = state[6];
   out_5876458652377630242[1] = state[7];
   out_5876458652377630242[2] = state[8];
}
void H_14(double *state, double *unused, double *out_3817943344000131709) {
   out_3817943344000131709[0] = 0;
   out_3817943344000131709[1] = 0;
   out_3817943344000131709[2] = 0;
   out_3817943344000131709[3] = 0;
   out_3817943344000131709[4] = 0;
   out_3817943344000131709[5] = 0;
   out_3817943344000131709[6] = 1;
   out_3817943344000131709[7] = 0;
   out_3817943344000131709[8] = 0;
   out_3817943344000131709[9] = 0;
   out_3817943344000131709[10] = 0;
   out_3817943344000131709[11] = 0;
   out_3817943344000131709[12] = 0;
   out_3817943344000131709[13] = 0;
   out_3817943344000131709[14] = 0;
   out_3817943344000131709[15] = 0;
   out_3817943344000131709[16] = 0;
   out_3817943344000131709[17] = 0;
   out_3817943344000131709[18] = 0;
   out_3817943344000131709[19] = 0;
   out_3817943344000131709[20] = 0;
   out_3817943344000131709[21] = 0;
   out_3817943344000131709[22] = 0;
   out_3817943344000131709[23] = 0;
   out_3817943344000131709[24] = 0;
   out_3817943344000131709[25] = 1;
   out_3817943344000131709[26] = 0;
   out_3817943344000131709[27] = 0;
   out_3817943344000131709[28] = 0;
   out_3817943344000131709[29] = 0;
   out_3817943344000131709[30] = 0;
   out_3817943344000131709[31] = 0;
   out_3817943344000131709[32] = 0;
   out_3817943344000131709[33] = 0;
   out_3817943344000131709[34] = 0;
   out_3817943344000131709[35] = 0;
   out_3817943344000131709[36] = 0;
   out_3817943344000131709[37] = 0;
   out_3817943344000131709[38] = 0;
   out_3817943344000131709[39] = 0;
   out_3817943344000131709[40] = 0;
   out_3817943344000131709[41] = 0;
   out_3817943344000131709[42] = 0;
   out_3817943344000131709[43] = 0;
   out_3817943344000131709[44] = 1;
   out_3817943344000131709[45] = 0;
   out_3817943344000131709[46] = 0;
   out_3817943344000131709[47] = 0;
   out_3817943344000131709[48] = 0;
   out_3817943344000131709[49] = 0;
   out_3817943344000131709[50] = 0;
   out_3817943344000131709[51] = 0;
   out_3817943344000131709[52] = 0;
   out_3817943344000131709[53] = 0;
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

void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_4, H_4, NULL, in_z, in_R, in_ea, MAHA_THRESH_4);
}
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_10, H_10, NULL, in_z, in_R, in_ea, MAHA_THRESH_10);
}
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_13, H_13, NULL, in_z, in_R, in_ea, MAHA_THRESH_13);
}
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_14, H_14, NULL, in_z, in_R, in_ea, MAHA_THRESH_14);
}
void pose_err_fun(double *nom_x, double *delta_x, double *out_7519798370927896678) {
  err_fun(nom_x, delta_x, out_7519798370927896678);
}
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_7487201815754910304) {
  inv_err_fun(nom_x, true_x, out_7487201815754910304);
}
void pose_H_mod_fun(double *state, double *out_1163177465718205104) {
  H_mod_fun(state, out_1163177465718205104);
}
void pose_f_fun(double *state, double dt, double *out_3990854090903749199) {
  f_fun(state,  dt, out_3990854090903749199);
}
void pose_F_fun(double *state, double dt, double *out_1836760290158182993) {
  F_fun(state,  dt, out_1836760290158182993);
}
void pose_h_4(double *state, double *unused, double *out_2491156385417327206) {
  h_4(state, unused, out_2491156385417327206);
}
void pose_H_4(double *state, double *unused, double *out_7781184200339616238) {
  H_4(state, unused, out_7781184200339616238);
}
void pose_h_10(double *state, double *unused, double *out_935983163405023118) {
  h_10(state, unused, out_935983163405023118);
}
void pose_H_10(double *state, double *unused, double *out_250545266026384824) {
  H_10(state, unused, out_250545266026384824);
}
void pose_h_13(double *state, double *unused, double *out_2877352012270184476) {
  h_13(state, unused, out_2877352012270184476);
}
void pose_H_13(double *state, double *unused, double *out_4568910375007283437) {
  H_13(state, unused, out_4568910375007283437);
}
void pose_h_14(double *state, double *unused, double *out_5876458652377630242) {
  h_14(state, unused, out_5876458652377630242);
}
void pose_H_14(double *state, double *unused, double *out_3817943344000131709) {
  H_14(state, unused, out_3817943344000131709);
}
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt) {
  predict(in_x, in_P, in_Q, dt);
}
}

const EKF pose = {
  .name = "pose",
  .kinds = { 4, 10, 13, 14 },
  .feature_kinds = {  },
  .f_fun = pose_f_fun,
  .F_fun = pose_F_fun,
  .err_fun = pose_err_fun,
  .inv_err_fun = pose_inv_err_fun,
  .H_mod_fun = pose_H_mod_fun,
  .predict = pose_predict,
  .hs = {
    { 4, pose_h_4 },
    { 10, pose_h_10 },
    { 13, pose_h_13 },
    { 14, pose_h_14 },
  },
  .Hs = {
    { 4, pose_H_4 },
    { 10, pose_H_10 },
    { 13, pose_H_13 },
    { 14, pose_H_14 },
  },
  .updates = {
    { 4, pose_update_4 },
    { 10, pose_update_10 },
    { 13, pose_update_13 },
    { 14, pose_update_14 },
  },
  .Hes = {
  },
  .sets = {
  },
  .extra_routines = {
  },
};

ekf_lib_init(pose)
