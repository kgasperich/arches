#include "matrix.h"

// ctypes handler interfacing
extern "C" {

// DMatrix constructors
DMatrix<float> *DMatrix_ctor_c_f32(idx_t m, idx_t n, float fill) {
    return new DMatrix<float>(m, n, fill);
}

DMatrix<float> *DMatrix_ctor_a_f32(idx_t m, idx_t n, float *fill) {
    return new DMatrix<float>(m, n, fill);
}

DMatrix<double> *DMatrix_ctor_c_f64(idx_t m, idx_t n, double fill) {
    return new DMatrix<double>(m, n, fill);
}

DMatrix<double> *DMatrix_ctor_a_f64(idx_t m, idx_t n, double *fill) {
    return new DMatrix<double>(m, n, fill);
}

// DMatrix pointer returns
float *DMatrix_get_arr_ptr_f32(DMatrix<float> *A) { return A->A; }
double *DMatrix_get_arr_ptr_f64(DMatrix<double> *A) { return A->A; }

// DMatrix destructors : TODO: test if necessary
void DMatrix_dtor_f32(DMatrix<float> *A) { delete A; }
void DMatrix_dtor_f64(DMatrix<double> *A) { delete A; }

// SymCSRMatrix constructors
SymCSRMatrix<float> *SymCSRMatrix_ctor_f32(idx_t m, idx_t n, idx_t *arr_p, idx_t *arr_c,
                                           float *arr_v) {
    return new SymCSRMatrix<float>(m, n, arr_p, arr_c, arr_v);
}

SymCSRMatrix<double> *SymCSRMatrix_ctor_f64(idx_t m, idx_t n, idx_t *arr_p, idx_t *arr_c,
                                            double *arr_v) {
    return new SymCSRMatrix<double>(m, n, arr_p, arr_c, arr_v);
}

// SymCSRMatrix destructors
void SymCSRMatrix_dtor_f32(SymCSRMatrix<float> *A) { delete A; }
void SymCSRMatrix_dtor_f64(SymCSRMatrix<double> *A) { delete A; }

// SymCSRMatrix pointer returns
idx_t *SymCSRMatrix_get_ap_ptr_f32(SymCSRMatrix<float> *A) { return A->A_p; }
idx_t *SymCSRMatrix_get_ap_ptr_f64(SymCSRMatrix<double> *A) { return A->A_p; }

idx_t *SymCSRMatrix_get_ac_ptr_f32(SymCSRMatrix<float> *A) { return A->A_c; }
idx_t *SymCSRMatrix_get_ac_ptr_f64(SymCSRMatrix<double> *A) { return A->A_c; }

idx_t *SymCSRMatrix_get_av_ptr_f32(SymCSRMatrix<float> *A) { return A->A_v; }
idx_t *SymCSRMatrix_get_av_ptr_f64(SymCSRMatrix<double> *A) { return A->A_v; }
}