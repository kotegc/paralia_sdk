import numpy as np
import pytest

from paralia_sdk.geometry import (
    Mesh, align_mesh_to_world_z, read_mesh, write_mesh,
    read_stl_raw, weld_triangle_soup, write_stl_bytes, read_mesh_bytes,
)


def _tetrahedron() -> Mesh:
    verts = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ])
    faces = np.array([
        [0, 1, 2],
        [0, 1, 3],
        [0, 2, 3],
        [1, 2, 3],
    ], dtype=np.int32)
    return Mesh(vertices=verts, faces=faces)


def test_mesh_post_init_shapes():
    mesh = _tetrahedron()
    assert mesh.vertex_count == 4
    assert mesh.face_count == 4
    assert mesh.vertices.dtype == np.float64


@pytest.mark.parametrize("ext", [".stl", ".obj", ".ply", ".3mf"])
def test_roundtrip_all_formats(tmp_path, ext):
    mesh = _tetrahedron()
    path = tmp_path / f"mesh{ext}"
    write_mesh(mesh, str(path))
    loaded = read_mesh(str(path))
    assert loaded.vertex_count == mesh.vertex_count
    assert loaded.face_count == mesh.face_count
    assert np.allclose(sorted(loaded.vertices.tolist()), sorted(mesh.vertices.tolist()))


def test_stl_bytes_roundtrip():
    mesh = _tetrahedron()
    data = write_stl_bytes(mesh)
    loaded = read_mesh_bytes(data, ".stl")
    assert loaded.vertex_count == mesh.vertex_count


def test_read_stl_raw_and_weld(tmp_path):
    mesh = _tetrahedron()
    path = tmp_path / "mesh.stl"
    from paralia_sdk.geometry import write_stl
    write_stl(mesh, str(path))
    raw = read_stl_raw(str(path))
    assert raw.shape == (mesh.face_count * 3, 3)
    welded = weld_triangle_soup(raw)
    assert welded.vertex_count == mesh.vertex_count


def test_align_mesh_to_world_z_axis_is_unit():
    mesh = _tetrahedron()
    result = align_mesh_to_world_z(mesh)
    axis_norm = np.linalg.norm(result.principal_axis)
    assert abs(axis_norm - 1.0) < 1e-6
    # Re-running alignment on an already-aligned mesh should be near-idempotent
    # in terms of vertex count / topology (not a proprietary-pipeline claim,
    # just a sanity check the vendored math didn't get mangled in transit).
    result2 = align_mesh_to_world_z(result.mesh)
    assert result2.mesh.vertex_count == mesh.vertex_count


def test_align_too_few_vertices_does_not_raise():
    mesh = Mesh(vertices=np.array([[0.0, 0.0, 0.0]]), faces=np.empty((0, 3), dtype=np.int32))
    result = align_mesh_to_world_z(mesh)
    assert result.message == "Mesh has too few vertices."
