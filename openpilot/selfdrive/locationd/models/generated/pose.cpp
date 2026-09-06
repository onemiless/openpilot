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
void err_fun(double *nom_x, double *delta_x, double *out_8898640593533968832) {
   out_8898640593533968832[0] = delta_x[0] + nom_x[0];
   out_8898640593533968832[1] = delta_x[1] + nom_x[1];
   out_8898640593533968832[2] = delta_x[2] + nom_x[2];
   out_8898640593533968832[3] = delta_x[3] + nom_x[3];
   out_8898640593533968832[4] = delta_x[4] + nom_x[4];
   out_8898640593533968832[5] = delta_x[5] + nom_x[5];
   out_8898640593533968832[6] = delta_x[6] + nom_x[6];
   out_8898640593533968832[7] = delta_x[7] + nom_x[7];
   out_8898640593533968832[8] = delta_x[8] + nom_x[8];
   out_8898640593533968832[9] = delta_x[9] + nom_x[9];
   out_8898640593533968832[10] = delta_x[10] + nom_x[10];
   out_8898640593533968832[11] = delta_x[11] + nom_x[11];
   out_8898640593533968832[12] = delta_x[12] + nom_x[12];
   out_8898640593533968832[13] = delta_x[13] + nom_x[13];
   out_8898640593533968832[14] = delta_x[14] + nom_x[14];
   out_8898640593533968832[15] = delta_x[15] + nom_x[15];
   out_8898640593533968832[16] = delta_x[16] + nom_x[16];
   out_8898640593533968832[17] = delta_x[17] + nom_x[17];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_3435172889934915688) {
   out_3435172889934915688[0] = -nom_x[0] + true_x[0];
   out_3435172889934915688[1] = -nom_x[1] + true_x[1];
   out_3435172889934915688[2] = -nom_x[2] + true_x[2];
   out_3435172889934915688[3] = -nom_x[3] + true_x[3];
   out_3435172889934915688[4] = -nom_x[4] + true_x[4];
   out_3435172889934915688[5] = -nom_x[5] + true_x[5];
   out_3435172889934915688[6] = -nom_x[6] + true_x[6];
   out_3435172889934915688[7] = -nom_x[7] + true_x[7];
   out_3435172889934915688[8] = -nom_x[8] + true_x[8];
   out_3435172889934915688[9] = -nom_x[9] + true_x[9];
   out_3435172889934915688[10] = -nom_x[10] + true_x[10];
   out_3435172889934915688[11] = -nom_x[11] + true_x[11];
   out_3435172889934915688[12] = -nom_x[12] + true_x[12];
   out_3435172889934915688[13] = -nom_x[13] + true_x[13];
   out_3435172889934915688[14] = -nom_x[14] + true_x[14];
   out_3435172889934915688[15] = -nom_x[15] + true_x[15];
   out_3435172889934915688[16] = -nom_x[16] + true_x[16];
   out_3435172889934915688[17] = -nom_x[17] + true_x[17];
}
void H_mod_fun(double *state, double *out_8426427664152767868) {
   out_8426427664152767868[0] = 1.0;
   out_8426427664152767868[1] = 0.0;
   out_8426427664152767868[2] = 0.0;
   out_8426427664152767868[3] = 0.0;
   out_8426427664152767868[4] = 0.0;
   out_8426427664152767868[5] = 0.0;
   out_8426427664152767868[6] = 0.0;
   out_8426427664152767868[7] = 0.0;
   out_8426427664152767868[8] = 0.0;
   out_8426427664152767868[9] = 0.0;
   out_8426427664152767868[10] = 0.0;
   out_8426427664152767868[11] = 0.0;
   out_8426427664152767868[12] = 0.0;
   out_8426427664152767868[13] = 0.0;
   out_8426427664152767868[14] = 0.0;
   out_8426427664152767868[15] = 0.0;
   out_8426427664152767868[16] = 0.0;
   out_8426427664152767868[17] = 0.0;
   out_8426427664152767868[18] = 0.0;
   out_8426427664152767868[19] = 1.0;
   out_8426427664152767868[20] = 0.0;
   out_8426427664152767868[21] = 0.0;
   out_8426427664152767868[22] = 0.0;
   out_8426427664152767868[23] = 0.0;
   out_8426427664152767868[24] = 0.0;
   out_8426427664152767868[25] = 0.0;
   out_8426427664152767868[26] = 0.0;
   out_8426427664152767868[27] = 0.0;
   out_8426427664152767868[28] = 0.0;
   out_8426427664152767868[29] = 0.0;
   out_8426427664152767868[30] = 0.0;
   out_8426427664152767868[31] = 0.0;
   out_8426427664152767868[32] = 0.0;
   out_8426427664152767868[33] = 0.0;
   out_8426427664152767868[34] = 0.0;
   out_8426427664152767868[35] = 0.0;
   out_8426427664152767868[36] = 0.0;
   out_8426427664152767868[37] = 0.0;
   out_8426427664152767868[38] = 1.0;
   out_8426427664152767868[39] = 0.0;
   out_8426427664152767868[40] = 0.0;
   out_8426427664152767868[41] = 0.0;
   out_8426427664152767868[42] = 0.0;
   out_8426427664152767868[43] = 0.0;
   out_8426427664152767868[44] = 0.0;
   out_8426427664152767868[45] = 0.0;
   out_8426427664152767868[46] = 0.0;
   out_8426427664152767868[47] = 0.0;
   out_8426427664152767868[48] = 0.0;
   out_8426427664152767868[49] = 0.0;
   out_8426427664152767868[50] = 0.0;
   out_8426427664152767868[51] = 0.0;
   out_8426427664152767868[52] = 0.0;
   out_8426427664152767868[53] = 0.0;
   out_8426427664152767868[54] = 0.0;
   out_8426427664152767868[55] = 0.0;
   out_8426427664152767868[56] = 0.0;
   out_8426427664152767868[57] = 1.0;
   out_8426427664152767868[58] = 0.0;
   out_8426427664152767868[59] = 0.0;
   out_8426427664152767868[60] = 0.0;
   out_8426427664152767868[61] = 0.0;
   out_8426427664152767868[62] = 0.0;
   out_8426427664152767868[63] = 0.0;
   out_8426427664152767868[64] = 0.0;
   out_8426427664152767868[65] = 0.0;
   out_8426427664152767868[66] = 0.0;
   out_8426427664152767868[67] = 0.0;
   out_8426427664152767868[68] = 0.0;
   out_8426427664152767868[69] = 0.0;
   out_8426427664152767868[70] = 0.0;
   out_8426427664152767868[71] = 0.0;
   out_8426427664152767868[72] = 0.0;
   out_8426427664152767868[73] = 0.0;
   out_8426427664152767868[74] = 0.0;
   out_8426427664152767868[75] = 0.0;
   out_8426427664152767868[76] = 1.0;
   out_8426427664152767868[77] = 0.0;
   out_8426427664152767868[78] = 0.0;
   out_8426427664152767868[79] = 0.0;
   out_8426427664152767868[80] = 0.0;
   out_8426427664152767868[81] = 0.0;
   out_8426427664152767868[82] = 0.0;
   out_8426427664152767868[83] = 0.0;
   out_8426427664152767868[84] = 0.0;
   out_8426427664152767868[85] = 0.0;
   out_8426427664152767868[86] = 0.0;
   out_8426427664152767868[87] = 0.0;
   out_8426427664152767868[88] = 0.0;
   out_8426427664152767868[89] = 0.0;
   out_8426427664152767868[90] = 0.0;
   out_8426427664152767868[91] = 0.0;
   out_8426427664152767868[92] = 0.0;
   out_8426427664152767868[93] = 0.0;
   out_8426427664152767868[94] = 0.0;
   out_8426427664152767868[95] = 1.0;
   out_8426427664152767868[96] = 0.0;
   out_8426427664152767868[97] = 0.0;
   out_8426427664152767868[98] = 0.0;
   out_8426427664152767868[99] = 0.0;
   out_8426427664152767868[100] = 0.0;
   out_8426427664152767868[101] = 0.0;
   out_8426427664152767868[102] = 0.0;
   out_8426427664152767868[103] = 0.0;
   out_8426427664152767868[104] = 0.0;
   out_8426427664152767868[105] = 0.0;
   out_8426427664152767868[106] = 0.0;
   out_8426427664152767868[107] = 0.0;
   out_8426427664152767868[108] = 0.0;
   out_8426427664152767868[109] = 0.0;
   out_8426427664152767868[110] = 0.0;
   out_8426427664152767868[111] = 0.0;
   out_8426427664152767868[112] = 0.0;
   out_8426427664152767868[113] = 0.0;
   out_8426427664152767868[114] = 1.0;
   out_8426427664152767868[115] = 0.0;
   out_8426427664152767868[116] = 0.0;
   out_8426427664152767868[117] = 0.0;
   out_8426427664152767868[118] = 0.0;
   out_8426427664152767868[119] = 0.0;
   out_8426427664152767868[120] = 0.0;
   out_8426427664152767868[121] = 0.0;
   out_8426427664152767868[122] = 0.0;
   out_8426427664152767868[123] = 0.0;
   out_8426427664152767868[124] = 0.0;
   out_8426427664152767868[125] = 0.0;
   out_8426427664152767868[126] = 0.0;
   out_8426427664152767868[127] = 0.0;
   out_8426427664152767868[128] = 0.0;
   out_8426427664152767868[129] = 0.0;
   out_8426427664152767868[130] = 0.0;
   out_8426427664152767868[131] = 0.0;
   out_8426427664152767868[132] = 0.0;
   out_8426427664152767868[133] = 1.0;
   out_8426427664152767868[134] = 0.0;
   out_8426427664152767868[135] = 0.0;
   out_8426427664152767868[136] = 0.0;
   out_8426427664152767868[137] = 0.0;
   out_8426427664152767868[138] = 0.0;
   out_8426427664152767868[139] = 0.0;
   out_8426427664152767868[140] = 0.0;
   out_8426427664152767868[141] = 0.0;
   out_8426427664152767868[142] = 0.0;
   out_8426427664152767868[143] = 0.0;
   out_8426427664152767868[144] = 0.0;
   out_8426427664152767868[145] = 0.0;
   out_8426427664152767868[146] = 0.0;
   out_8426427664152767868[147] = 0.0;
   out_8426427664152767868[148] = 0.0;
   out_8426427664152767868[149] = 0.0;
   out_8426427664152767868[150] = 0.0;
   out_8426427664152767868[151] = 0.0;
   out_8426427664152767868[152] = 1.0;
   out_8426427664152767868[153] = 0.0;
   out_8426427664152767868[154] = 0.0;
   out_8426427664152767868[155] = 0.0;
   out_8426427664152767868[156] = 0.0;
   out_8426427664152767868[157] = 0.0;
   out_8426427664152767868[158] = 0.0;
   out_8426427664152767868[159] = 0.0;
   out_8426427664152767868[160] = 0.0;
   out_8426427664152767868[161] = 0.0;
   out_8426427664152767868[162] = 0.0;
   out_8426427664152767868[163] = 0.0;
   out_8426427664152767868[164] = 0.0;
   out_8426427664152767868[165] = 0.0;
   out_8426427664152767868[166] = 0.0;
   out_8426427664152767868[167] = 0.0;
   out_8426427664152767868[168] = 0.0;
   out_8426427664152767868[169] = 0.0;
   out_8426427664152767868[170] = 0.0;
   out_8426427664152767868[171] = 1.0;
   out_8426427664152767868[172] = 0.0;
   out_8426427664152767868[173] = 0.0;
   out_8426427664152767868[174] = 0.0;
   out_8426427664152767868[175] = 0.0;
   out_8426427664152767868[176] = 0.0;
   out_8426427664152767868[177] = 0.0;
   out_8426427664152767868[178] = 0.0;
   out_8426427664152767868[179] = 0.0;
   out_8426427664152767868[180] = 0.0;
   out_8426427664152767868[181] = 0.0;
   out_8426427664152767868[182] = 0.0;
   out_8426427664152767868[183] = 0.0;
   out_8426427664152767868[184] = 0.0;
   out_8426427664152767868[185] = 0.0;
   out_8426427664152767868[186] = 0.0;
   out_8426427664152767868[187] = 0.0;
   out_8426427664152767868[188] = 0.0;
   out_8426427664152767868[189] = 0.0;
   out_8426427664152767868[190] = 1.0;
   out_8426427664152767868[191] = 0.0;
   out_8426427664152767868[192] = 0.0;
   out_8426427664152767868[193] = 0.0;
   out_8426427664152767868[194] = 0.0;
   out_8426427664152767868[195] = 0.0;
   out_8426427664152767868[196] = 0.0;
   out_8426427664152767868[197] = 0.0;
   out_8426427664152767868[198] = 0.0;
   out_8426427664152767868[199] = 0.0;
   out_8426427664152767868[200] = 0.0;
   out_8426427664152767868[201] = 0.0;
   out_8426427664152767868[202] = 0.0;
   out_8426427664152767868[203] = 0.0;
   out_8426427664152767868[204] = 0.0;
   out_8426427664152767868[205] = 0.0;
   out_8426427664152767868[206] = 0.0;
   out_8426427664152767868[207] = 0.0;
   out_8426427664152767868[208] = 0.0;
   out_8426427664152767868[209] = 1.0;
   out_8426427664152767868[210] = 0.0;
   out_8426427664152767868[211] = 0.0;
   out_8426427664152767868[212] = 0.0;
   out_8426427664152767868[213] = 0.0;
   out_8426427664152767868[214] = 0.0;
   out_8426427664152767868[215] = 0.0;
   out_8426427664152767868[216] = 0.0;
   out_8426427664152767868[217] = 0.0;
   out_8426427664152767868[218] = 0.0;
   out_8426427664152767868[219] = 0.0;
   out_8426427664152767868[220] = 0.0;
   out_8426427664152767868[221] = 0.0;
   out_8426427664152767868[222] = 0.0;
   out_8426427664152767868[223] = 0.0;
   out_8426427664152767868[224] = 0.0;
   out_8426427664152767868[225] = 0.0;
   out_8426427664152767868[226] = 0.0;
   out_8426427664152767868[227] = 0.0;
   out_8426427664152767868[228] = 1.0;
   out_8426427664152767868[229] = 0.0;
   out_8426427664152767868[230] = 0.0;
   out_8426427664152767868[231] = 0.0;
   out_8426427664152767868[232] = 0.0;
   out_8426427664152767868[233] = 0.0;
   out_8426427664152767868[234] = 0.0;
   out_8426427664152767868[235] = 0.0;
   out_8426427664152767868[236] = 0.0;
   out_8426427664152767868[237] = 0.0;
   out_8426427664152767868[238] = 0.0;
   out_8426427664152767868[239] = 0.0;
   out_8426427664152767868[240] = 0.0;
   out_8426427664152767868[241] = 0.0;
   out_8426427664152767868[242] = 0.0;
   out_8426427664152767868[243] = 0.0;
   out_8426427664152767868[244] = 0.0;
   out_8426427664152767868[245] = 0.0;
   out_8426427664152767868[246] = 0.0;
   out_8426427664152767868[247] = 1.0;
   out_8426427664152767868[248] = 0.0;
   out_8426427664152767868[249] = 0.0;
   out_8426427664152767868[250] = 0.0;
   out_8426427664152767868[251] = 0.0;
   out_8426427664152767868[252] = 0.0;
   out_8426427664152767868[253] = 0.0;
   out_8426427664152767868[254] = 0.0;
   out_8426427664152767868[255] = 0.0;
   out_8426427664152767868[256] = 0.0;
   out_8426427664152767868[257] = 0.0;
   out_8426427664152767868[258] = 0.0;
   out_8426427664152767868[259] = 0.0;
   out_8426427664152767868[260] = 0.0;
   out_8426427664152767868[261] = 0.0;
   out_8426427664152767868[262] = 0.0;
   out_8426427664152767868[263] = 0.0;
   out_8426427664152767868[264] = 0.0;
   out_8426427664152767868[265] = 0.0;
   out_8426427664152767868[266] = 1.0;
   out_8426427664152767868[267] = 0.0;
   out_8426427664152767868[268] = 0.0;
   out_8426427664152767868[269] = 0.0;
   out_8426427664152767868[270] = 0.0;
   out_8426427664152767868[271] = 0.0;
   out_8426427664152767868[272] = 0.0;
   out_8426427664152767868[273] = 0.0;
   out_8426427664152767868[274] = 0.0;
   out_8426427664152767868[275] = 0.0;
   out_8426427664152767868[276] = 0.0;
   out_8426427664152767868[277] = 0.0;
   out_8426427664152767868[278] = 0.0;
   out_8426427664152767868[279] = 0.0;
   out_8426427664152767868[280] = 0.0;
   out_8426427664152767868[281] = 0.0;
   out_8426427664152767868[282] = 0.0;
   out_8426427664152767868[283] = 0.0;
   out_8426427664152767868[284] = 0.0;
   out_8426427664152767868[285] = 1.0;
   out_8426427664152767868[286] = 0.0;
   out_8426427664152767868[287] = 0.0;
   out_8426427664152767868[288] = 0.0;
   out_8426427664152767868[289] = 0.0;
   out_8426427664152767868[290] = 0.0;
   out_8426427664152767868[291] = 0.0;
   out_8426427664152767868[292] = 0.0;
   out_8426427664152767868[293] = 0.0;
   out_8426427664152767868[294] = 0.0;
   out_8426427664152767868[295] = 0.0;
   out_8426427664152767868[296] = 0.0;
   out_8426427664152767868[297] = 0.0;
   out_8426427664152767868[298] = 0.0;
   out_8426427664152767868[299] = 0.0;
   out_8426427664152767868[300] = 0.0;
   out_8426427664152767868[301] = 0.0;
   out_8426427664152767868[302] = 0.0;
   out_8426427664152767868[303] = 0.0;
   out_8426427664152767868[304] = 1.0;
   out_8426427664152767868[305] = 0.0;
   out_8426427664152767868[306] = 0.0;
   out_8426427664152767868[307] = 0.0;
   out_8426427664152767868[308] = 0.0;
   out_8426427664152767868[309] = 0.0;
   out_8426427664152767868[310] = 0.0;
   out_8426427664152767868[311] = 0.0;
   out_8426427664152767868[312] = 0.0;
   out_8426427664152767868[313] = 0.0;
   out_8426427664152767868[314] = 0.0;
   out_8426427664152767868[315] = 0.0;
   out_8426427664152767868[316] = 0.0;
   out_8426427664152767868[317] = 0.0;
   out_8426427664152767868[318] = 0.0;
   out_8426427664152767868[319] = 0.0;
   out_8426427664152767868[320] = 0.0;
   out_8426427664152767868[321] = 0.0;
   out_8426427664152767868[322] = 0.0;
   out_8426427664152767868[323] = 1.0;
}
void f_fun(double *state, double dt, double *out_4211470879648912048) {
   out_4211470879648912048[0] = atan2((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), -(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]));
   out_4211470879648912048[1] = asin(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]));
   out_4211470879648912048[2] = atan2(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), -(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]));
   out_4211470879648912048[3] = dt*state[12] + state[3];
   out_4211470879648912048[4] = dt*state[13] + state[4];
   out_4211470879648912048[5] = dt*state[14] + state[5];
   out_4211470879648912048[6] = state[6];
   out_4211470879648912048[7] = state[7];
   out_4211470879648912048[8] = state[8];
   out_4211470879648912048[9] = state[9];
   out_4211470879648912048[10] = state[10];
   out_4211470879648912048[11] = state[11];
   out_4211470879648912048[12] = state[12];
   out_4211470879648912048[13] = state[13];
   out_4211470879648912048[14] = state[14];
   out_4211470879648912048[15] = state[15];
   out_4211470879648912048[16] = state[16];
   out_4211470879648912048[17] = state[17];
}
void F_fun(double *state, double dt, double *out_6812913047568660000) {
   out_6812913047568660000[0] = ((-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*cos(state[0])*cos(state[1]) - sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*cos(state[0])*cos(state[1]) - sin(dt*state[6])*sin(state[0])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_6812913047568660000[1] = ((-sin(dt*state[6])*sin(dt*state[8]) - sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*cos(state[1]) - (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*sin(state[1]) - sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(state[0]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*sin(state[1]) + (-sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) + sin(dt*state[8])*cos(dt*state[6]))*cos(state[1]) - sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(state[0]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_6812913047568660000[2] = 0;
   out_6812913047568660000[3] = 0;
   out_6812913047568660000[4] = 0;
   out_6812913047568660000[5] = 0;
   out_6812913047568660000[6] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(dt*cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) - dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_6812913047568660000[7] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*sin(dt*state[7])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[6])*sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) - dt*sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[7])*cos(dt*state[6])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[8])*sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]) - dt*sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_6812913047568660000[8] = ((dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((dt*sin(dt*state[6])*sin(dt*state[8]) + dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_6812913047568660000[9] = 0;
   out_6812913047568660000[10] = 0;
   out_6812913047568660000[11] = 0;
   out_6812913047568660000[12] = 0;
   out_6812913047568660000[13] = 0;
   out_6812913047568660000[14] = 0;
   out_6812913047568660000[15] = 0;
   out_6812913047568660000[16] = 0;
   out_6812913047568660000[17] = 0;
   out_6812913047568660000[18] = (-sin(dt*state[7])*sin(state[0])*cos(state[1]) - sin(dt*state[8])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_6812913047568660000[19] = (-sin(dt*state[7])*sin(state[1])*cos(state[0]) + sin(dt*state[8])*sin(state[0])*sin(state[1])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_6812913047568660000[20] = 0;
   out_6812913047568660000[21] = 0;
   out_6812913047568660000[22] = 0;
   out_6812913047568660000[23] = 0;
   out_6812913047568660000[24] = 0;
   out_6812913047568660000[25] = (dt*sin(dt*state[7])*sin(dt*state[8])*sin(state[0])*cos(state[1]) - dt*sin(dt*state[7])*sin(state[1])*cos(dt*state[8]) + dt*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_6812913047568660000[26] = (-dt*sin(dt*state[8])*sin(state[1])*cos(dt*state[7]) - dt*sin(state[0])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_6812913047568660000[27] = 0;
   out_6812913047568660000[28] = 0;
   out_6812913047568660000[29] = 0;
   out_6812913047568660000[30] = 0;
   out_6812913047568660000[31] = 0;
   out_6812913047568660000[32] = 0;
   out_6812913047568660000[33] = 0;
   out_6812913047568660000[34] = 0;
   out_6812913047568660000[35] = 0;
   out_6812913047568660000[36] = ((sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_6812913047568660000[37] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-sin(dt*state[7])*sin(state[2])*cos(state[0])*cos(state[1]) + sin(dt*state[8])*sin(state[0])*sin(state[2])*cos(dt*state[7])*cos(state[1]) - sin(state[1])*sin(state[2])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(-sin(dt*state[7])*cos(state[0])*cos(state[1])*cos(state[2]) + sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1])*cos(state[2]) - sin(state[1])*cos(dt*state[7])*cos(dt*state[8])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_6812913047568660000[38] = ((-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (-sin(state[0])*sin(state[1])*sin(state[2]) - cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_6812913047568660000[39] = 0;
   out_6812913047568660000[40] = 0;
   out_6812913047568660000[41] = 0;
   out_6812913047568660000[42] = 0;
   out_6812913047568660000[43] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(dt*(sin(state[0])*cos(state[2]) - sin(state[1])*sin(state[2])*cos(state[0]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*sin(state[2])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(dt*(-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_6812913047568660000[44] = (dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*sin(state[2])*cos(dt*state[7])*cos(state[1]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + (dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[7])*cos(state[1])*cos(state[2]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_6812913047568660000[45] = 0;
   out_6812913047568660000[46] = 0;
   out_6812913047568660000[47] = 0;
   out_6812913047568660000[48] = 0;
   out_6812913047568660000[49] = 0;
   out_6812913047568660000[50] = 0;
   out_6812913047568660000[51] = 0;
   out_6812913047568660000[52] = 0;
   out_6812913047568660000[53] = 0;
   out_6812913047568660000[54] = 0;
   out_6812913047568660000[55] = 0;
   out_6812913047568660000[56] = 0;
   out_6812913047568660000[57] = 1;
   out_6812913047568660000[58] = 0;
   out_6812913047568660000[59] = 0;
   out_6812913047568660000[60] = 0;
   out_6812913047568660000[61] = 0;
   out_6812913047568660000[62] = 0;
   out_6812913047568660000[63] = 0;
   out_6812913047568660000[64] = 0;
   out_6812913047568660000[65] = 0;
   out_6812913047568660000[66] = dt;
   out_6812913047568660000[67] = 0;
   out_6812913047568660000[68] = 0;
   out_6812913047568660000[69] = 0;
   out_6812913047568660000[70] = 0;
   out_6812913047568660000[71] = 0;
   out_6812913047568660000[72] = 0;
   out_6812913047568660000[73] = 0;
   out_6812913047568660000[74] = 0;
   out_6812913047568660000[75] = 0;
   out_6812913047568660000[76] = 1;
   out_6812913047568660000[77] = 0;
   out_6812913047568660000[78] = 0;
   out_6812913047568660000[79] = 0;
   out_6812913047568660000[80] = 0;
   out_6812913047568660000[81] = 0;
   out_6812913047568660000[82] = 0;
   out_6812913047568660000[83] = 0;
   out_6812913047568660000[84] = 0;
   out_6812913047568660000[85] = dt;
   out_6812913047568660000[86] = 0;
   out_6812913047568660000[87] = 0;
   out_6812913047568660000[88] = 0;
   out_6812913047568660000[89] = 0;
   out_6812913047568660000[90] = 0;
   out_6812913047568660000[91] = 0;
   out_6812913047568660000[92] = 0;
   out_6812913047568660000[93] = 0;
   out_6812913047568660000[94] = 0;
   out_6812913047568660000[95] = 1;
   out_6812913047568660000[96] = 0;
   out_6812913047568660000[97] = 0;
   out_6812913047568660000[98] = 0;
   out_6812913047568660000[99] = 0;
   out_6812913047568660000[100] = 0;
   out_6812913047568660000[101] = 0;
   out_6812913047568660000[102] = 0;
   out_6812913047568660000[103] = 0;
   out_6812913047568660000[104] = dt;
   out_6812913047568660000[105] = 0;
   out_6812913047568660000[106] = 0;
   out_6812913047568660000[107] = 0;
   out_6812913047568660000[108] = 0;
   out_6812913047568660000[109] = 0;
   out_6812913047568660000[110] = 0;
   out_6812913047568660000[111] = 0;
   out_6812913047568660000[112] = 0;
   out_6812913047568660000[113] = 0;
   out_6812913047568660000[114] = 1;
   out_6812913047568660000[115] = 0;
   out_6812913047568660000[116] = 0;
   out_6812913047568660000[117] = 0;
   out_6812913047568660000[118] = 0;
   out_6812913047568660000[119] = 0;
   out_6812913047568660000[120] = 0;
   out_6812913047568660000[121] = 0;
   out_6812913047568660000[122] = 0;
   out_6812913047568660000[123] = 0;
   out_6812913047568660000[124] = 0;
   out_6812913047568660000[125] = 0;
   out_6812913047568660000[126] = 0;
   out_6812913047568660000[127] = 0;
   out_6812913047568660000[128] = 0;
   out_6812913047568660000[129] = 0;
   out_6812913047568660000[130] = 0;
   out_6812913047568660000[131] = 0;
   out_6812913047568660000[132] = 0;
   out_6812913047568660000[133] = 1;
   out_6812913047568660000[134] = 0;
   out_6812913047568660000[135] = 0;
   out_6812913047568660000[136] = 0;
   out_6812913047568660000[137] = 0;
   out_6812913047568660000[138] = 0;
   out_6812913047568660000[139] = 0;
   out_6812913047568660000[140] = 0;
   out_6812913047568660000[141] = 0;
   out_6812913047568660000[142] = 0;
   out_6812913047568660000[143] = 0;
   out_6812913047568660000[144] = 0;
   out_6812913047568660000[145] = 0;
   out_6812913047568660000[146] = 0;
   out_6812913047568660000[147] = 0;
   out_6812913047568660000[148] = 0;
   out_6812913047568660000[149] = 0;
   out_6812913047568660000[150] = 0;
   out_6812913047568660000[151] = 0;
   out_6812913047568660000[152] = 1;
   out_6812913047568660000[153] = 0;
   out_6812913047568660000[154] = 0;
   out_6812913047568660000[155] = 0;
   out_6812913047568660000[156] = 0;
   out_6812913047568660000[157] = 0;
   out_6812913047568660000[158] = 0;
   out_6812913047568660000[159] = 0;
   out_6812913047568660000[160] = 0;
   out_6812913047568660000[161] = 0;
   out_6812913047568660000[162] = 0;
   out_6812913047568660000[163] = 0;
   out_6812913047568660000[164] = 0;
   out_6812913047568660000[165] = 0;
   out_6812913047568660000[166] = 0;
   out_6812913047568660000[167] = 0;
   out_6812913047568660000[168] = 0;
   out_6812913047568660000[169] = 0;
   out_6812913047568660000[170] = 0;
   out_6812913047568660000[171] = 1;
   out_6812913047568660000[172] = 0;
   out_6812913047568660000[173] = 0;
   out_6812913047568660000[174] = 0;
   out_6812913047568660000[175] = 0;
   out_6812913047568660000[176] = 0;
   out_6812913047568660000[177] = 0;
   out_6812913047568660000[178] = 0;
   out_6812913047568660000[179] = 0;
   out_6812913047568660000[180] = 0;
   out_6812913047568660000[181] = 0;
   out_6812913047568660000[182] = 0;
   out_6812913047568660000[183] = 0;
   out_6812913047568660000[184] = 0;
   out_6812913047568660000[185] = 0;
   out_6812913047568660000[186] = 0;
   out_6812913047568660000[187] = 0;
   out_6812913047568660000[188] = 0;
   out_6812913047568660000[189] = 0;
   out_6812913047568660000[190] = 1;
   out_6812913047568660000[191] = 0;
   out_6812913047568660000[192] = 0;
   out_6812913047568660000[193] = 0;
   out_6812913047568660000[194] = 0;
   out_6812913047568660000[195] = 0;
   out_6812913047568660000[196] = 0;
   out_6812913047568660000[197] = 0;
   out_6812913047568660000[198] = 0;
   out_6812913047568660000[199] = 0;
   out_6812913047568660000[200] = 0;
   out_6812913047568660000[201] = 0;
   out_6812913047568660000[202] = 0;
   out_6812913047568660000[203] = 0;
   out_6812913047568660000[204] = 0;
   out_6812913047568660000[205] = 0;
   out_6812913047568660000[206] = 0;
   out_6812913047568660000[207] = 0;
   out_6812913047568660000[208] = 0;
   out_6812913047568660000[209] = 1;
   out_6812913047568660000[210] = 0;
   out_6812913047568660000[211] = 0;
   out_6812913047568660000[212] = 0;
   out_6812913047568660000[213] = 0;
   out_6812913047568660000[214] = 0;
   out_6812913047568660000[215] = 0;
   out_6812913047568660000[216] = 0;
   out_6812913047568660000[217] = 0;
   out_6812913047568660000[218] = 0;
   out_6812913047568660000[219] = 0;
   out_6812913047568660000[220] = 0;
   out_6812913047568660000[221] = 0;
   out_6812913047568660000[222] = 0;
   out_6812913047568660000[223] = 0;
   out_6812913047568660000[224] = 0;
   out_6812913047568660000[225] = 0;
   out_6812913047568660000[226] = 0;
   out_6812913047568660000[227] = 0;
   out_6812913047568660000[228] = 1;
   out_6812913047568660000[229] = 0;
   out_6812913047568660000[230] = 0;
   out_6812913047568660000[231] = 0;
   out_6812913047568660000[232] = 0;
   out_6812913047568660000[233] = 0;
   out_6812913047568660000[234] = 0;
   out_6812913047568660000[235] = 0;
   out_6812913047568660000[236] = 0;
   out_6812913047568660000[237] = 0;
   out_6812913047568660000[238] = 0;
   out_6812913047568660000[239] = 0;
   out_6812913047568660000[240] = 0;
   out_6812913047568660000[241] = 0;
   out_6812913047568660000[242] = 0;
   out_6812913047568660000[243] = 0;
   out_6812913047568660000[244] = 0;
   out_6812913047568660000[245] = 0;
   out_6812913047568660000[246] = 0;
   out_6812913047568660000[247] = 1;
   out_6812913047568660000[248] = 0;
   out_6812913047568660000[249] = 0;
   out_6812913047568660000[250] = 0;
   out_6812913047568660000[251] = 0;
   out_6812913047568660000[252] = 0;
   out_6812913047568660000[253] = 0;
   out_6812913047568660000[254] = 0;
   out_6812913047568660000[255] = 0;
   out_6812913047568660000[256] = 0;
   out_6812913047568660000[257] = 0;
   out_6812913047568660000[258] = 0;
   out_6812913047568660000[259] = 0;
   out_6812913047568660000[260] = 0;
   out_6812913047568660000[261] = 0;
   out_6812913047568660000[262] = 0;
   out_6812913047568660000[263] = 0;
   out_6812913047568660000[264] = 0;
   out_6812913047568660000[265] = 0;
   out_6812913047568660000[266] = 1;
   out_6812913047568660000[267] = 0;
   out_6812913047568660000[268] = 0;
   out_6812913047568660000[269] = 0;
   out_6812913047568660000[270] = 0;
   out_6812913047568660000[271] = 0;
   out_6812913047568660000[272] = 0;
   out_6812913047568660000[273] = 0;
   out_6812913047568660000[274] = 0;
   out_6812913047568660000[275] = 0;
   out_6812913047568660000[276] = 0;
   out_6812913047568660000[277] = 0;
   out_6812913047568660000[278] = 0;
   out_6812913047568660000[279] = 0;
   out_6812913047568660000[280] = 0;
   out_6812913047568660000[281] = 0;
   out_6812913047568660000[282] = 0;
   out_6812913047568660000[283] = 0;
   out_6812913047568660000[284] = 0;
   out_6812913047568660000[285] = 1;
   out_6812913047568660000[286] = 0;
   out_6812913047568660000[287] = 0;
   out_6812913047568660000[288] = 0;
   out_6812913047568660000[289] = 0;
   out_6812913047568660000[290] = 0;
   out_6812913047568660000[291] = 0;
   out_6812913047568660000[292] = 0;
   out_6812913047568660000[293] = 0;
   out_6812913047568660000[294] = 0;
   out_6812913047568660000[295] = 0;
   out_6812913047568660000[296] = 0;
   out_6812913047568660000[297] = 0;
   out_6812913047568660000[298] = 0;
   out_6812913047568660000[299] = 0;
   out_6812913047568660000[300] = 0;
   out_6812913047568660000[301] = 0;
   out_6812913047568660000[302] = 0;
   out_6812913047568660000[303] = 0;
   out_6812913047568660000[304] = 1;
   out_6812913047568660000[305] = 0;
   out_6812913047568660000[306] = 0;
   out_6812913047568660000[307] = 0;
   out_6812913047568660000[308] = 0;
   out_6812913047568660000[309] = 0;
   out_6812913047568660000[310] = 0;
   out_6812913047568660000[311] = 0;
   out_6812913047568660000[312] = 0;
   out_6812913047568660000[313] = 0;
   out_6812913047568660000[314] = 0;
   out_6812913047568660000[315] = 0;
   out_6812913047568660000[316] = 0;
   out_6812913047568660000[317] = 0;
   out_6812913047568660000[318] = 0;
   out_6812913047568660000[319] = 0;
   out_6812913047568660000[320] = 0;
   out_6812913047568660000[321] = 0;
   out_6812913047568660000[322] = 0;
   out_6812913047568660000[323] = 1;
}
void h_4(double *state, double *unused, double *out_6777878803091675943) {
   out_6777878803091675943[0] = state[6] + state[9];
   out_6777878803091675943[1] = state[7] + state[10];
   out_6777878803091675943[2] = state[8] + state[11];
}
void H_4(double *state, double *unused, double *out_3322402639485405722) {
   out_3322402639485405722[0] = 0;
   out_3322402639485405722[1] = 0;
   out_3322402639485405722[2] = 0;
   out_3322402639485405722[3] = 0;
   out_3322402639485405722[4] = 0;
   out_3322402639485405722[5] = 0;
   out_3322402639485405722[6] = 1;
   out_3322402639485405722[7] = 0;
   out_3322402639485405722[8] = 0;
   out_3322402639485405722[9] = 1;
   out_3322402639485405722[10] = 0;
   out_3322402639485405722[11] = 0;
   out_3322402639485405722[12] = 0;
   out_3322402639485405722[13] = 0;
   out_3322402639485405722[14] = 0;
   out_3322402639485405722[15] = 0;
   out_3322402639485405722[16] = 0;
   out_3322402639485405722[17] = 0;
   out_3322402639485405722[18] = 0;
   out_3322402639485405722[19] = 0;
   out_3322402639485405722[20] = 0;
   out_3322402639485405722[21] = 0;
   out_3322402639485405722[22] = 0;
   out_3322402639485405722[23] = 0;
   out_3322402639485405722[24] = 0;
   out_3322402639485405722[25] = 1;
   out_3322402639485405722[26] = 0;
   out_3322402639485405722[27] = 0;
   out_3322402639485405722[28] = 1;
   out_3322402639485405722[29] = 0;
   out_3322402639485405722[30] = 0;
   out_3322402639485405722[31] = 0;
   out_3322402639485405722[32] = 0;
   out_3322402639485405722[33] = 0;
   out_3322402639485405722[34] = 0;
   out_3322402639485405722[35] = 0;
   out_3322402639485405722[36] = 0;
   out_3322402639485405722[37] = 0;
   out_3322402639485405722[38] = 0;
   out_3322402639485405722[39] = 0;
   out_3322402639485405722[40] = 0;
   out_3322402639485405722[41] = 0;
   out_3322402639485405722[42] = 0;
   out_3322402639485405722[43] = 0;
   out_3322402639485405722[44] = 1;
   out_3322402639485405722[45] = 0;
   out_3322402639485405722[46] = 0;
   out_3322402639485405722[47] = 1;
   out_3322402639485405722[48] = 0;
   out_3322402639485405722[49] = 0;
   out_3322402639485405722[50] = 0;
   out_3322402639485405722[51] = 0;
   out_3322402639485405722[52] = 0;
   out_3322402639485405722[53] = 0;
}
void h_10(double *state, double *unused, double *out_7706867558898837591) {
   out_7706867558898837591[0] = 9.8100000000000005*sin(state[1]) - state[4]*state[8] + state[5]*state[7] + state[12] + state[15];
   out_7706867558898837591[1] = -9.8100000000000005*sin(state[0])*cos(state[1]) + state[3]*state[8] - state[5]*state[6] + state[13] + state[16];
   out_7706867558898837591[2] = -9.8100000000000005*cos(state[0])*cos(state[1]) - state[3]*state[7] + state[4]*state[6] + state[14] + state[17];
}
void H_10(double *state, double *unused, double *out_1882782654140805881) {
   out_1882782654140805881[0] = 0;
   out_1882782654140805881[1] = 9.8100000000000005*cos(state[1]);
   out_1882782654140805881[2] = 0;
   out_1882782654140805881[3] = 0;
   out_1882782654140805881[4] = -state[8];
   out_1882782654140805881[5] = state[7];
   out_1882782654140805881[6] = 0;
   out_1882782654140805881[7] = state[5];
   out_1882782654140805881[8] = -state[4];
   out_1882782654140805881[9] = 0;
   out_1882782654140805881[10] = 0;
   out_1882782654140805881[11] = 0;
   out_1882782654140805881[12] = 1;
   out_1882782654140805881[13] = 0;
   out_1882782654140805881[14] = 0;
   out_1882782654140805881[15] = 1;
   out_1882782654140805881[16] = 0;
   out_1882782654140805881[17] = 0;
   out_1882782654140805881[18] = -9.8100000000000005*cos(state[0])*cos(state[1]);
   out_1882782654140805881[19] = 9.8100000000000005*sin(state[0])*sin(state[1]);
   out_1882782654140805881[20] = 0;
   out_1882782654140805881[21] = state[8];
   out_1882782654140805881[22] = 0;
   out_1882782654140805881[23] = -state[6];
   out_1882782654140805881[24] = -state[5];
   out_1882782654140805881[25] = 0;
   out_1882782654140805881[26] = state[3];
   out_1882782654140805881[27] = 0;
   out_1882782654140805881[28] = 0;
   out_1882782654140805881[29] = 0;
   out_1882782654140805881[30] = 0;
   out_1882782654140805881[31] = 1;
   out_1882782654140805881[32] = 0;
   out_1882782654140805881[33] = 0;
   out_1882782654140805881[34] = 1;
   out_1882782654140805881[35] = 0;
   out_1882782654140805881[36] = 9.8100000000000005*sin(state[0])*cos(state[1]);
   out_1882782654140805881[37] = 9.8100000000000005*sin(state[1])*cos(state[0]);
   out_1882782654140805881[38] = 0;
   out_1882782654140805881[39] = -state[7];
   out_1882782654140805881[40] = state[6];
   out_1882782654140805881[41] = 0;
   out_1882782654140805881[42] = state[4];
   out_1882782654140805881[43] = -state[3];
   out_1882782654140805881[44] = 0;
   out_1882782654140805881[45] = 0;
   out_1882782654140805881[46] = 0;
   out_1882782654140805881[47] = 0;
   out_1882782654140805881[48] = 0;
   out_1882782654140805881[49] = 0;
   out_1882782654140805881[50] = 1;
   out_1882782654140805881[51] = 0;
   out_1882782654140805881[52] = 0;
   out_1882782654140805881[53] = 1;
}
void h_13(double *state, double *unused, double *out_7433113681699853348) {
   out_7433113681699853348[0] = state[3];
   out_7433113681699853348[1] = state[4];
   out_7433113681699853348[2] = state[5];
}
void H_13(double *state, double *unused, double *out_4288228568831295207) {
   out_4288228568831295207[0] = 0;
   out_4288228568831295207[1] = 0;
   out_4288228568831295207[2] = 0;
   out_4288228568831295207[3] = 1;
   out_4288228568831295207[4] = 0;
   out_4288228568831295207[5] = 0;
   out_4288228568831295207[6] = 0;
   out_4288228568831295207[7] = 0;
   out_4288228568831295207[8] = 0;
   out_4288228568831295207[9] = 0;
   out_4288228568831295207[10] = 0;
   out_4288228568831295207[11] = 0;
   out_4288228568831295207[12] = 0;
   out_4288228568831295207[13] = 0;
   out_4288228568831295207[14] = 0;
   out_4288228568831295207[15] = 0;
   out_4288228568831295207[16] = 0;
   out_4288228568831295207[17] = 0;
   out_4288228568831295207[18] = 0;
   out_4288228568831295207[19] = 0;
   out_4288228568831295207[20] = 0;
   out_4288228568831295207[21] = 0;
   out_4288228568831295207[22] = 1;
   out_4288228568831295207[23] = 0;
   out_4288228568831295207[24] = 0;
   out_4288228568831295207[25] = 0;
   out_4288228568831295207[26] = 0;
   out_4288228568831295207[27] = 0;
   out_4288228568831295207[28] = 0;
   out_4288228568831295207[29] = 0;
   out_4288228568831295207[30] = 0;
   out_4288228568831295207[31] = 0;
   out_4288228568831295207[32] = 0;
   out_4288228568831295207[33] = 0;
   out_4288228568831295207[34] = 0;
   out_4288228568831295207[35] = 0;
   out_4288228568831295207[36] = 0;
   out_4288228568831295207[37] = 0;
   out_4288228568831295207[38] = 0;
   out_4288228568831295207[39] = 0;
   out_4288228568831295207[40] = 0;
   out_4288228568831295207[41] = 1;
   out_4288228568831295207[42] = 0;
   out_4288228568831295207[43] = 0;
   out_4288228568831295207[44] = 0;
   out_4288228568831295207[45] = 0;
   out_4288228568831295207[46] = 0;
   out_4288228568831295207[47] = 0;
   out_4288228568831295207[48] = 0;
   out_4288228568831295207[49] = 0;
   out_4288228568831295207[50] = 0;
   out_4288228568831295207[51] = 0;
   out_4288228568831295207[52] = 0;
   out_4288228568831295207[53] = 0;
}
void h_14(double *state, double *unused, double *out_7770713869499660906) {
   out_7770713869499660906[0] = state[6];
   out_7770713869499660906[1] = state[7];
   out_7770713869499660906[2] = state[8];
}
void H_14(double *state, double *unused, double *out_6405191071780778018) {
   out_6405191071780778018[0] = 0;
   out_6405191071780778018[1] = 0;
   out_6405191071780778018[2] = 0;
   out_6405191071780778018[3] = 0;
   out_6405191071780778018[4] = 0;
   out_6405191071780778018[5] = 0;
   out_6405191071780778018[6] = 1;
   out_6405191071780778018[7] = 0;
   out_6405191071780778018[8] = 0;
   out_6405191071780778018[9] = 0;
   out_6405191071780778018[10] = 0;
   out_6405191071780778018[11] = 0;
   out_6405191071780778018[12] = 0;
   out_6405191071780778018[13] = 0;
   out_6405191071780778018[14] = 0;
   out_6405191071780778018[15] = 0;
   out_6405191071780778018[16] = 0;
   out_6405191071780778018[17] = 0;
   out_6405191071780778018[18] = 0;
   out_6405191071780778018[19] = 0;
   out_6405191071780778018[20] = 0;
   out_6405191071780778018[21] = 0;
   out_6405191071780778018[22] = 0;
   out_6405191071780778018[23] = 0;
   out_6405191071780778018[24] = 0;
   out_6405191071780778018[25] = 1;
   out_6405191071780778018[26] = 0;
   out_6405191071780778018[27] = 0;
   out_6405191071780778018[28] = 0;
   out_6405191071780778018[29] = 0;
   out_6405191071780778018[30] = 0;
   out_6405191071780778018[31] = 0;
   out_6405191071780778018[32] = 0;
   out_6405191071780778018[33] = 0;
   out_6405191071780778018[34] = 0;
   out_6405191071780778018[35] = 0;
   out_6405191071780778018[36] = 0;
   out_6405191071780778018[37] = 0;
   out_6405191071780778018[38] = 0;
   out_6405191071780778018[39] = 0;
   out_6405191071780778018[40] = 0;
   out_6405191071780778018[41] = 0;
   out_6405191071780778018[42] = 0;
   out_6405191071780778018[43] = 0;
   out_6405191071780778018[44] = 1;
   out_6405191071780778018[45] = 0;
   out_6405191071780778018[46] = 0;
   out_6405191071780778018[47] = 0;
   out_6405191071780778018[48] = 0;
   out_6405191071780778018[49] = 0;
   out_6405191071780778018[50] = 0;
   out_6405191071780778018[51] = 0;
   out_6405191071780778018[52] = 0;
   out_6405191071780778018[53] = 0;
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
void pose_err_fun(double *nom_x, double *delta_x, double *out_8898640593533968832) {
  err_fun(nom_x, delta_x, out_8898640593533968832);
}
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_3435172889934915688) {
  inv_err_fun(nom_x, true_x, out_3435172889934915688);
}
void pose_H_mod_fun(double *state, double *out_8426427664152767868) {
  H_mod_fun(state, out_8426427664152767868);
}
void pose_f_fun(double *state, double dt, double *out_4211470879648912048) {
  f_fun(state,  dt, out_4211470879648912048);
}
void pose_F_fun(double *state, double dt, double *out_6812913047568660000) {
  F_fun(state,  dt, out_6812913047568660000);
}
void pose_h_4(double *state, double *unused, double *out_6777878803091675943) {
  h_4(state, unused, out_6777878803091675943);
}
void pose_H_4(double *state, double *unused, double *out_3322402639485405722) {
  H_4(state, unused, out_3322402639485405722);
}
void pose_h_10(double *state, double *unused, double *out_7706867558898837591) {
  h_10(state, unused, out_7706867558898837591);
}
void pose_H_10(double *state, double *unused, double *out_1882782654140805881) {
  H_10(state, unused, out_1882782654140805881);
}
void pose_h_13(double *state, double *unused, double *out_7433113681699853348) {
  h_13(state, unused, out_7433113681699853348);
}
void pose_H_13(double *state, double *unused, double *out_4288228568831295207) {
  H_13(state, unused, out_4288228568831295207);
}
void pose_h_14(double *state, double *unused, double *out_7770713869499660906) {
  h_14(state, unused, out_7770713869499660906);
}
void pose_H_14(double *state, double *unused, double *out_6405191071780778018) {
  H_14(state, unused, out_6405191071780778018);
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
