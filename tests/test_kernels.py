import pathlib
import unittest

import numpy as np
from test_types import Test_f32, Test_f64
from tqdm import tqdm

from arches.determinant import det_t, spin_det_t
from arches.drivers import Hamiltonian_one_electron, Hamiltonian_two_electrons_determinant_driven
from arches.fundamental_types import Determinant as det_ref
from arches.integral_indexing_utils import canonical_idx4, compound_idx4, compound_idx4_reverse
from arches.integrals import JChunkFactory, load_integrals_into_chunks
from arches.io import load_integrals
from arches.linked_object import f32_p, idx_t


class FakeComm:
    # to avoid initializing MPI for just tests
    def __init__(self, rank, size):
        self.rank = rank
        self.size = size

    def Get_rank(self):
        return self.rank

    def Get_size(self):
        return self.size


class FilteredDict:
    def __init__(self, data):
        self._data = data

    def __getitem__(self, key):
        try:
            return self._data[key]
        except KeyError:
            return 0.0

    def items(self):
        return self._data.items()


class Test_Kernel_Fixture(unittest.TestCase):
    __test__ = False

    @classmethod
    def setUpClass(cls):
        run_folder = pathlib.Path(__file__).parent.resolve()
        fp = run_folder.joinpath("../data/nh3.5det.fcidump")
        # fp = run_folder.joinpath("../data/f2_631g.18det.fcidump")
        # fp = run_folder.joinpath("../data/c2_eq_hf_dz.fcidump")
        cls.fp = fp

        _, _, J_oe, J_te = load_integrals(str(fp))

        N_orbs, N_elec, E0, chunks = load_integrals_into_chunks(
            str(fp), FakeComm(0, 1), dtype=cls.dtype
        )

        _, _, _, batched_chunks = load_integrals_into_chunks(
            str(fp), FakeComm(0, 1), chunk_size=32, dtype=cls.dtype
        )

        cls.N_mos = N_orbs
        cls.E0 = E0
        cls.chunks = chunks
        cls.batched_chunks = batched_chunks
        cls.ref_J_oe = J_oe
        cls.ref_J_te = J_te

        max_orb = N_elec // 2
        ground_state = det_t(
            N_orbs,
            spin_det_t(N_orbs, occ=True, max_orb=max_orb),
            spin_det_t(N_orbs, occ=True, max_orb=max_orb),
        )

        cls.ground_state = ground_state
        cls.ground_connected = ground_state.generate_connected_dets()

        alpha_orbs = ground_state.alpha.as_orb_list
        beta_orbs = ground_state.beta.as_orb_list
        h_constraint = alpha_orbs[-3:]
        p_constraint = tuple(set([x for x in range(N_orbs)]).difference(set(h_constraint)))[-4:]

        constraint = (h_constraint, p_constraint)
        cls.ground_constrained = ground_state.generate_connected_dets(constraint)

        cls.ref_ground_state = det_ref(alpha_orbs, beta_orbs)

        cls.ref_dets = [
            det_ref(d.alpha.as_orb_list, d.beta.as_orb_list) for d in cls.ground_connected
        ]

        cls.ref_constrained_dets = [
            det_ref(d.alpha.as_orb_list, d.beta.as_orb_list) for d in cls.ground_constrained
        ]

    def filter_chunks(self, cat, batched=False):
        if batched:
            return [chunk for chunk in self.batched_chunks if chunk.category == cat]
        else:
            return [chunk for chunk in self.chunks if chunk.category == cat]

    def get_ref_te_driver(self, cat):
        fact = JChunkFactory(self.N_mos, cat, None)
        ref_dict = {k: self.ref_J_te[k] for k in fact.idx_iter}
        return Hamiltonian_two_electrons_determinant_driven(FilteredDict(ref_dict))


class Test_pt2_Kernels(Test_Kernel_Fixture):
    __test__ = False

    def launch_denom_kernel(self, kernel, chunk, ext_dets, res):
        kernel(
            chunk.J.p,
            chunk.idx.p,
            idx_t(chunk.chunk_size),
            idx_t(1),
            ext_dets.det_pointer,
            ext_dets.N_dets,
            res.arr.p,
        )

    def launch_num_kernel(self, kernel, chunk, int_dets, psi_coef, ext_dets, res):
        kernel(
            chunk.J.p,
            chunk.idx.p,
            idx_t(chunk.chunk_size),
            int_dets.det_pointer,
            psi_coef.arr.p,
            int_dets.N_dets,
            idx_t(1),
            ext_dets.det_pointer,
            ext_dets.N_dets,
            res.arr.p,
        )

    def run_denom_test(self, cat):
        chunk = self.filter_chunks(cat)[0]
        kernel = chunk.pt2_kernels[1]
        pt2_d = self.LArray(N=self.ground_connected.N_dets, fill=0.0)

        ref_driver = self.get_ref_te_driver(cat)
        ref_pt2_d = np.array([ref_driver.H_ii(det_J) for det_J in self.ref_dets])

        self.launch_denom_kernel(kernel, chunk, self.ground_connected, pt2_d)
        self.assertTrue(np.allclose(ref_pt2_d, pt2_d.arr.np_arr, rtol=self.rtol, atol=self.atol))

    def run_batched_denom_test(self, cat, custom_batches=None):
        if custom_batches is None:
            chunks = self.filter_chunks(cat, batched=True)
        else:
            chunks = custom_batches

        self.assertTrue(len(chunks) > 1)
        kernel = chunks[0].pt2_kernels[1]
        pt2_d = self.LArray(N=self.ground_connected.N_dets, fill=0.0)

        ref_driver = self.get_ref_te_driver(cat)
        ref_pt2_d = np.array([ref_driver.H_ii(det_J) for det_J in self.ref_dets])

        for chunk in chunks:
            self.launch_denom_kernel(kernel, chunk, self.ground_connected, pt2_d)

        self.assertTrue(np.allclose(ref_pt2_d, pt2_d.arr.np_arr, rtol=self.rtol, atol=self.atol))

    def run_num_test(self, cat):
        ref_driver = self.get_ref_te_driver(cat)
        ref_res = np.zeros(len(self.ref_dets), dtype=self.dtype)

        det_I = self.ref_ground_state
        for j, det_J in enumerate(self.ref_dets):
            for idx, phase in ref_driver.H_ij_indices(det_I, det_J):
                ref_res[j] += phase * ref_driver.H_ijkl_orbital(*idx)

        chunk = self.filter_chunks(cat)[0]
        kernel = chunk.pt2_kernels[0]
        psi_coef = self.LArray(N=1, fill=1.0)
        pt2_n = self.LArray(N=self.ground_connected.N_dets, fill=0.0)

        self.launch_num_kernel(
            kernel, chunk, self.ground_state, psi_coef, self.ground_connected, pt2_n
        )
        self.assertTrue(np.allclose(ref_res, pt2_n.arr.np_arr, rtol=self.rtol, atol=self.atol))

    def run_batched_num_test(self, cat):
        ref_driver = self.get_ref_te_driver(cat)
        ref_res = np.zeros(len(self.ref_dets), dtype=self.dtype)

        det_I = self.ref_ground_state
        for j, det_J in enumerate(self.ref_dets):
            for idx, phase in ref_driver.H_ij_indices(det_I, det_J):
                ref_res[j] += phase * ref_driver.H_ijkl_orbital(*idx)

        chunks = self.filter_chunks(cat, batched=True)
        kernel = chunks[0].pt2_kernels[0]
        psi_coef = self.LArray(N=1, fill=1.0)
        pt2_n = self.LArray(N=self.ground_connected.N_dets, fill=0.0)

        for chunk in chunks:
            self.launch_num_kernel(
                kernel, chunk, self.ground_state, psi_coef, self.ground_connected, pt2_n
            )
        self.assertTrue(np.allclose(ref_res, pt2_n.arr.np_arr, rtol=self.rtol, atol=self.atol))

    def test_cat_A(self):
        self.run_denom_test("A")

    def test_cat_A_batched(self):
        ## since test dump only has 18 orbs, need to have smaller batches to test batched chunks for A
        _, _, _, batched_chunks = load_integrals_into_chunks(
            str(self.fp), FakeComm(0, 1), chunk_size=8, dtype=self.dtype
        )
        A_chunks = [chunk for chunk in batched_chunks if chunk.category == "A"]
        self.run_batched_denom_test("A", A_chunks)

    def test_cat_B(self):
        self.run_denom_test("B")

    def test_cat_B_batched(self):
        self.run_batched_denom_test("B")

    def test_cat_C(self):
        self.run_num_test("C")

    def test_cat_C_batched(self):
        self.run_batched_num_test("C")

    def test_cat_D(self):
        self.run_num_test("D")

    def test_cat_D_batched(self):
        self.run_batched_num_test("D")

    def test_cat_E(self):
        self.run_num_test("E")

    def test_cat_E_batched(self):
        self.run_batched_num_test("E")

    def test_cat_F_num(self):
        self.run_num_test("F")

    def test_cat_F_batched(self):
        self.run_batched_num_test("F")

    def test_cat_F_denom(self):
        self.run_denom_test("F")

    def test_cat_F_denom_batched(self):
        self.run_batched_denom_test("F")

    def test_cat_G(self):
        self.run_num_test("G")

    def test_cat_G_batched(self):
        self.run_batched_num_test("G")


class Test_pt2_Kernels_f32(Test_f32, Test_pt2_Kernels):
    __test__ = True


class Test_pt2_Kernels_f64(Test_f64, Test_pt2_Kernels):
    __test__ = True


class Test_H_Kernels(Test_Kernel_Fixture):
    __test__ = False

    @classmethod
    def setUpClass(cls):
        super(Test_H_Kernels, cls).setUpClass()
        ref_dets = cls.ref_constrained_dets
        N_ref_dets = len(ref_dets)
        ref_entries = []
        for i in range(N_ref_dets):
            for j in range(i, N_ref_dets):
                exc = ref_dets[i].exc_degree(ref_dets[j])
                if exc[0] + exc[1] <= 2:
                    ref_entries.append((i, j))

        cls.ref_entries = ref_entries

        cls.H_structure = cls.ground_constrained.get_H_structure(cls.dtype)

    def test_H_structure(self):
        ref_set = set(self.ref_entries)
        test_entries = []
        for i in range(self.H_structure.m):
            row = i
            row_start = self.H_structure.A_p[row]
            row_end = self.H_structure.A_p[row + 1]
            test_entries.extend(
                [(row, self.H_structure.A_c[idx]) for idx in range(row_start, row_end)]
            )

        test_set = set(test_entries)
        self.assertEqual(ref_set, test_set)

    def launch_H_ii_kernel(self, kernel, chunk):
        kernel(
            chunk.J.p,
            chunk.idx.p,
            idx_t(chunk.chunk_size),
            self.ground_constrained.det_pointer,
            idx_t(self.ground_constrained.N_dets),
            self.H_structure.A_p.p,
            self.H_structure.A_v.p,
        )

    def launch_H_ij_kernel(self, kernel, chunk):
        kernel(
            chunk.J.p,
            chunk.idx.p,
            idx_t(chunk.chunk_size),
            self.ground_constrained.det_pointer,
            idx_t(self.ground_constrained.N_dets),
            self.H_structure.A_p.p,
            self.H_structure.A_c.p,
            self.H_structure.A_v.p,
        )

    def run_ii_test(self, cat):
        chunk = self.filter_chunks(cat)[0]
        kernel = chunk.H_kernels[1]

        ref_driver = self.get_ref_te_driver(cat)
        ref_H_ii = np.array([ref_driver.H_ii(det_J) for det_J in self.ref_constrained_dets])

        # Clear out result since H_structure is cached
        for i in range(self.H_structure.m):
            row_start = self.H_structure.A_p[i]
            self.H_structure.A_v[row_start] = 0.0

        self.launch_H_ii_kernel(kernel, chunk)
        test_H_ii = np.zeros(self.H_structure.m, dtype=self.dtype)
        for i in range(self.H_structure.m):
            row_start = self.H_structure.A_p[i]
            test_H_ii[i] = self.H_structure.A_v[row_start]

        self.assertTrue(np.allclose(ref_H_ii, test_H_ii, atol=self.atol, rtol=self.rtol))

    def run_batched_ii_test(self, cat, custom_batches=None):
        if custom_batches is None:
            chunks = self.filter_chunks(cat, batched=True)
        else:
            chunks = custom_batches

        kernel = chunks[0].H_kernels[1]
        self.assertTrue(len(chunks) > 1)

        ref_driver = self.get_ref_te_driver(cat)
        ref_H_ii = np.array([ref_driver.H_ii(det_J) for det_J in self.ref_constrained_dets])

        # Clear out result since H_structure is cached
        for i in range(self.H_structure.m):
            row_start = self.H_structure.A_p[i]
            self.H_structure.A_v[row_start] = 0.0

        for chunk in chunks:
            self.launch_H_ii_kernel(kernel, chunk)

        test_H_ii = np.zeros(self.H_structure.m, dtype=self.dtype)
        for i in range(self.H_structure.m):
            row_start = self.H_structure.A_p[i]
            test_H_ii[i] = self.H_structure.A_v[row_start]

        self.assertTrue(np.allclose(ref_H_ii, test_H_ii, atol=self.atol, rtol=self.rtol))

    def run_ij_test(self, cat):
        chunk = self.filter_chunks(cat)[0]
        kernel = chunk.H_kernels[0]
        ref_driver = self.get_ref_te_driver(cat)

        ref_H_ij = np.zeros((self.H_structure.m, self.H_structure.m), dtype=self.dtype)
        for i, j in self.ref_entries:
            if i == j:
                continue
            det_I = self.ref_constrained_dets[i]
            det_J = self.ref_constrained_dets[j]
            for idx, phase in ref_driver.H_ij_indices(det_I, det_J):
                ref_H_ij[i, j] += phase * ref_driver.H_ijkl_orbital(*idx)

        # Clear out result since H_structure is cached
        for i in range(self.H_structure.N_entries):
            self.H_structure.A_v[i] = 0.0

        self.launch_H_ij_kernel(kernel, chunk)
        test_H_ij = np.zeros_like(ref_H_ij)
        for i in range(self.H_structure.m):
            row_start = self.H_structure.A_p[i]
            row_end = self.H_structure.A_p[i + 1]
            for idx in range(row_start, row_end):
                j = self.H_structure.A_c[idx]
                val = self.H_structure.A_v[idx]
                test_H_ij[i, j] = val

        self.assertTrue(np.allclose(ref_H_ij, test_H_ij, atol=self.atol, rtol=self.rtol))

    def run_batched_ij_test(self, cat):
        chunks = self.filter_chunks(cat)
        kernel = chunks[0].H_kernels[0]
        ref_driver = self.get_ref_te_driver(cat)

        ref_H_ij = np.zeros((self.H_structure.m, self.H_structure.m), dtype=self.dtype)
        for i, j in self.ref_entries:
            if i == j:
                continue
            det_I = self.ref_constrained_dets[i]
            det_J = self.ref_constrained_dets[j]
            for idx, phase in ref_driver.H_ij_indices(det_I, det_J):
                ref_H_ij[i, j] += phase * ref_driver.H_ijkl_orbital(*idx)

        # Clear out result since H_structure is cached
        for i in range(self.H_structure.N_entries):
            self.H_structure.A_v[i] = 0.0

        for chunk in chunks:
            self.launch_H_ij_kernel(kernel, chunk)

        test_H_ij = np.zeros_like(ref_H_ij)
        for i in range(self.H_structure.m):
            row_start = self.H_structure.A_p[i]
            row_end = self.H_structure.A_p[i + 1]
            for idx in range(row_start, row_end):
                j = self.H_structure.A_c[idx]
                val = self.H_structure.A_v[idx]
                test_H_ij[i, j] = val

        self.assertTrue(np.allclose(ref_H_ij, test_H_ij, atol=self.atol, rtol=self.rtol))

    def test_cat_A(self):
        self.run_ii_test("A")

    def test_cat_A_batched(self):
        ## since test dump only has 18 orbs, need to have smaller batches to test batched chunks for A
        _, _, _, batched_chunks = load_integrals_into_chunks(
            str(self.fp), FakeComm(0, 1), chunk_size=8, dtype=self.dtype
        )
        A_chunks = [chunk for chunk in batched_chunks if chunk.category == "A"]
        self.run_batched_ii_test("A", A_chunks)

    def test_cat_B(self):
        self.run_ii_test("B")

    def test_cat_B_batched(self):
        self.run_batched_ii_test("B")

    def test_cat_C(self):
        self.run_ij_test("C")

    def test_cat_C_batched(self):
        self.run_batched_ij_test("C")

    def test_cat_D(self):
        self.run_ij_test("D")

    def test_cat_D_batched(self):
        self.run_batched_ij_test("D")

    def test_cat_E(self):
        self.run_ij_test("E")

    def test_cat_E_batched(self):
        self.run_batched_ij_test("E")

    def test_cat_F_ij(self):
        self.run_ij_test("F")

    def test_cat_F_ij_batched(self):
        self.run_batched_ij_test("F")

    def test_cat_F_ii(self):
        self.run_ii_test("F")

    def test_cat_F_ii_batched(self):
        self.run_batched_ii_test("F")

    def test_cat_G(self):
        self.run_ij_test("G")

    def test_cat_G_batched(self):
        self.run_batched_ij_test("G")


class Test_H_Kernels_f32(Test_f32, Test_H_Kernels):
    __test__ = True


class Test_H_Kernels_f64(Test_f64, Test_H_Kernels):
    __test__ = True
