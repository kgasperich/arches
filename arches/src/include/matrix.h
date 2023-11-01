#pragma once
#include <algorithm>
#include <memory>

typedef long long int idx_t;

// enum s_major { ROW, COL };
// TODO : figure out interface if we want both row and col major matrices
template <class T> class DMatrix {
  protected:
    std::unique_ptr<T[]> A_ptr;

  public:
    idx_t m; // row rank
    idx_t n; // col rank
    T *A;    // matrix entries
    // s_major storage;

    // TODO: adjust class for offload semantics
    // 1) In constructor, map A to target
    // 2) In constructor, store device pointer for A
    // 3) In destructor, make sure target is moved back/cleared

    // fill constructor
    template <class Y> DMatrix(idx_t M, idx_t N, Y fill_val) {
        m = M;
        n = N;

        std::unique_ptr<Y[]> p(new Y[m * n]);
        A_ptr = std::move(p);
        A = A_ptr.get();

        std::fill(A, A + m * n, fill_val);
    };

    // copy constructor // Is there a way to delegate the common code?
    template <class Y> DMatrix(idx_t M, idx_t N, Y *arr) {
        m = M;
        n = N;

        std::unique_ptr<Y[]> p(new Y[m * n]);
        A_ptr = std::move(p);
        A = A_ptr.get();

        std::copy(arr, arr + m * n, A);
    };

    // TODO: some form of slice assignment? In general, utilities for assigning, copying, and
    // returning submatrices

    ~DMatrix() = default;
};

template <class T> class SymCSRMatrix {
    // TODO: evaluate whether or not it would be useful to have list of list version, to convert
    // back and forth between

  protected:
    std::unique_ptr<idx_t[]> A_p_ptr;
    std::unique_ptr<idx_t[]> A_c_ptr;
    std::unique_ptr<T[]> A_v_ptr;

  public:
    idx_t m;    // row rank
    idx_t n;    // col rank
    idx_t *A_p; // row pointers
    idx_t *A_c; // col indices
    T *A_v;     // matrix entries

    // copy constructor only for now
    template <class Y> SymCSRMatrix(idx_t M, idx_t N, idx_t *arr_p, idx_t *arr_c, Y *arr_v) {
        m = M;
        n = N;

        // allocate row pointer array
        std::unique_ptr<idx_t[]> A_p_tmp(new idx_t[m + 1]);
        A_p_ptr = std::move(A_p_tmp);
        A_p = A_p_ptr.get();
        std::copy(arr_p, arr_p + m, A_p);

        // allocate col arr
        idx_t n_entries = A_p[m];
        std::unique_ptr<Y[]> A_c_tmp(new idx_t[n_entries]);
        A_c_ptr = std::move(A_c_tmp);
        A_c = A_c_ptr.get();
        std::copy(arr_c, arr_c + n_entries, A_c);

        // allocate values
        std::unique_ptr<Y[]> A_v_tmp(new Y[n_entries]);
        A_v_ptr = std::move(A_v_tmp);
        A_v = A_v_ptr.get();

        std::copy(arr, arr + m * n, A);
    };
};
