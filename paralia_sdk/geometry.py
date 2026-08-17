"""
Generic mesh I/O and PCA world-Z alignment — vendored from paradigm's
`core/types.py::Mesh`, `io/mesh_io.py`, and `core/align.py`, byte-for-byte
behavior-identical at the time of this split (2026-08-17).

This is a deliberate *copy*, not a shared import from paradigm: paradigm is
proprietary and parable (an open-source consumer of this SDK) must never
depend on paradigm's source, even indirectly through a "generic-looking"
utility module that happens to live inside paradigm's package. Everything in
this file is self-contained, dependency-free geometry math with no coupling
to paradigm's actual differentiated pipeline (SDF/liner/heatmap/cap
detection, all still exclusively in `paradigm/core/`) — hand-rolled mesh
format parsers and a textbook PCA-align-to-Z-axis operation.

Tradeoff, stated plainly: paradigm's own copies of this code are NOT
re-pointed at this module, so the two now drift independently rather than
sharing one source of truth. That's intentional here — re-pointing would
mean editing paradigm's `core/types.py`/`core/align.py`/`io/mesh_io.py` (real
pipeline-adjacent files) to depend on a new external package, which is a
larger-blast-radius change than duplicating ~500 lines of already-stable,
already-tested I/O code. If the two ever need to be reconciled, this file
and paradigm's `io/mesh_io.py`/`core/align.py` are the two copies to diff.
"""

from __future__ import annotations

import io
import struct
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

_3MF_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"

_PLY_TYPES = {  # name -> (struct_char, byte_size)
    "char": ("b", 1), "int8": ("b", 1),
    "uchar": ("B", 1), "uint8": ("B", 1),
    "short": ("h", 2), "int16": ("h", 2),
    "ushort": ("H", 2), "uint16": ("H", 2),
    "int": ("i", 4), "int32": ("i", 4),
    "uint": ("I", 4), "uint32": ("I", 4),
    "float": ("f", 4), "float32": ("f", 4),
    "double": ("d", 8), "float64": ("d", 8),
}


# ---------------------------------------------------------------------------
# Mesh
# ---------------------------------------------------------------------------

@dataclass
class Mesh:
    """A plain indexed face set. Faces may be triangles or quads.

    vertices : (N, 3) float64
    faces    : (M, K) int32, K in {3, 4}; quads are stored as 4-tuples.
    """

    vertices: np.ndarray
    faces: np.ndarray
    vertex_normals: Optional[np.ndarray] = None
    face_normals: Optional[np.ndarray] = None

    def __post_init__(self) -> None:
        self.vertices = np.asarray(self.vertices, dtype=np.float64).reshape(-1, 3)
        self.faces = np.asarray(self.faces)

    @property
    def vertex_count(self) -> int:
        return int(self.vertices.shape[0])

    @property
    def face_count(self) -> int:
        return int(self.faces.shape[0])


@dataclass
class AlignmentResult:
    """Output of PCA alignment."""

    mesh: Mesh
    principal_axis: np.ndarray  # (3,) unit vector, in ORIGINAL frame
    centroid: np.ndarray        # (3,) original-frame centroid
    message: str = ""


# ---------------------------------------------------------------------------
# OBJ
# ---------------------------------------------------------------------------

def _read_obj_fh(fh) -> Mesh:
    """Parse OBJ from any text file-like object."""
    verts: List[List[float]] = []
    faces: List[List[int]] = []
    for line in fh:
        if not line or line[0] not in "vf":
            continue
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "v":
            verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
        elif parts[0] == "f":
            # f a/b/c d/e/f ... -> take vertex index before first slash.
            idx = [int(p.split("/")[0]) for p in parts[1:]]
            # OBJ is 1-indexed; negative indices are relative.
            idx = [(i - 1) if i > 0 else (len(verts) + i) for i in idx]
            faces.append(idx)
    return _weld_indexed(np.asarray(verts, dtype=np.float64),
                         _triangulate_face_list(faces))


def read_obj(path: str) -> Mesh:
    with open(path, "r") as fh:
        return _read_obj_fh(fh)


def write_obj(mesh: Mesh, path: str) -> None:
    """Write an indexed mesh as ASCII OBJ (1-indexed faces, triangles only)."""
    with open(path, "w") as fh:
        for v in mesh.vertices:
            fh.write("v %.6f %.6f %.6f\n" % (v[0], v[1], v[2]))
        for f in _triangulate_faces(mesh.faces):
            fh.write("f %d %d %d\n" % (f[0] + 1, f[1] + 1, f[2] + 1))


def _triangulate_face_list(faces: List[List[int]]) -> np.ndarray:
    """Fan-triangulate any polygon faces to a uniform (M,3) int array."""
    tris = []
    for f in faces:
        if len(f) == 3:
            tris.append(f)
        elif len(f) >= 4:
            for i in range(1, len(f) - 1):
                tris.append([f[0], f[i], f[i + 1]])
    return np.asarray(tris, dtype=np.int32)


def _triangulate_faces(faces: np.ndarray) -> np.ndarray:
    """Fan-triangulate a uniform (M,3) or (M,4) face array. Writers only ever
    emit triangles (STL has no quad representation at all; keeping OBJ/PLY/3MF
    writers triangle-only too keeps one code path for all four formats)."""
    faces = np.asarray(faces)
    if faces.shape[1] == 3:
        return faces.astype(np.int32)
    return np.vstack([faces[:, [0, 1, 2]], faces[:, [0, 2, 3]]]).astype(np.int32)


# ---------------------------------------------------------------------------
# STL
# ---------------------------------------------------------------------------

_STL_TRIANGLE_DTYPE = np.dtype([
    ("normal", "<f4", (3,)),
    ("v0", "<f4", (3,)),
    ("v1", "<f4", (3,)),
    ("v2", "<f4", (3,)),
    ("attr", "<u2"),
])


def _parse_stl_binary_raw(fh) -> np.ndarray:
    """Parse binary STL, returning the raw (3*F,3) per-triangle vertex array,
    unwelded — every triangle's 3 vertices are independent, in file order."""
    fh.read(80)  # header
    (count,) = struct.unpack("<I", fh.read(4))
    records = np.frombuffer(fh.read(count * 50), dtype=_STL_TRIANGLE_DTYPE, count=count)
    tri_verts = np.empty((count * 3, 3), dtype=np.float64)
    tri_verts[0::3] = records["v0"]
    tri_verts[1::3] = records["v1"]
    tri_verts[2::3] = records["v2"]
    return tri_verts


def _read_stl_binary_fh(fh) -> Mesh:
    """Parse binary STL from a binary file-like (seeked to position 0)."""
    return _weld(_parse_stl_binary_raw(fh))


def read_stl_raw(path: str) -> np.ndarray:
    """Read a binary STL's raw per-triangle vertex array (3*F, 3), unwelded.

    Needed when external data is indexed against a mesh file's original
    per-triangle vertex order rather than a deduplicated/indexed mesh — e.g. a
    PCA component matrix trained directly on a specific STL's raw vertex
    layout. Ordinary mesh consumption should use read_mesh/read_stl instead."""
    with open(path, "rb") as fh:
        header = fh.read(5)
        fh.seek(0)
        if header == b"solid":
            data = fh.read()
            if b"facet normal" in data[:1024]:
                raise ValueError("read_stl_raw does not support ASCII STL")
            fh.seek(0)
        return _parse_stl_binary_raw(fh)


def _read_stl_ascii_fh(fh) -> Mesh:
    """Parse ASCII STL from any text file-like object."""
    coords = []
    for line in fh:
        s = line.strip()
        if s.startswith("vertex"):
            _, x, y, z = s.split()
            coords.append([float(x), float(y), float(z)])
    return _weld(np.asarray(coords, dtype=np.float64))


def _read_stl_fh(fh) -> Mesh:
    """Dispatch binary vs ASCII STL from a binary file-like."""
    header = fh.read(5)
    fh.seek(0)
    if header == b"solid":
        # Could still be binary with a "solid" header; sniff further.
        data = fh.read()
        fh.seek(0)
        if b"facet normal" in data[:1024]:
            return _read_stl_ascii_fh(io.StringIO(data.decode("ascii", errors="replace")))
    return _read_stl_binary_fh(fh)


def read_stl(path: str) -> Mesh:
    with open(path, "rb") as fh:
        return _read_stl_fh(fh)


def _write_stl_fh(mesh: Mesh, fh) -> None:
    tris = _triangulate_faces(mesh.faces)
    verts = mesh.vertices
    v0, v1, v2 = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]

    normals = np.cross(v1 - v0, v2 - v0)
    norms = np.linalg.norm(normals, axis=1)
    safe = norms > 1e-12
    normals[safe] /= norms[safe, None]
    normals[~safe] = 0.0

    records = np.zeros(tris.shape[0], dtype=_STL_TRIANGLE_DTYPE)
    records["normal"] = normals
    records["v0"] = v0
    records["v1"] = v1
    records["v2"] = v2

    fh.write(b"\x00" * 80)
    fh.write(struct.pack("<I", tris.shape[0]))
    fh.write(records.tobytes())


def write_stl(mesh: Mesh, path: str) -> None:
    """Write an indexed mesh as binary STL (quads fan-triangulated first —
    STL has no polygon representation)."""
    with open(path, "wb") as fh:
        _write_stl_fh(mesh, fh)


def write_stl_bytes(mesh: Mesh) -> bytes:
    buf = io.BytesIO()
    _write_stl_fh(mesh, buf)
    return buf.getvalue()


def _weld(tri_verts: np.ndarray, decimals: int = 6) -> Mesh:
    """Weld coincident vertices (rounded to `decimals`) into an indexed mesh."""
    keys = np.round(tri_verts, decimals)
    uniq, inverse = np.unique(keys, axis=0, return_inverse=True)
    faces = inverse.reshape(-1, 3).astype(np.int32)
    return Mesh(vertices=uniq, faces=faces)


def weld_triangle_soup(tri_verts: np.ndarray, decimals: int = 6) -> Mesh:
    """Public entry point for welding a raw (3*F,3) per-triangle vertex array
    (no face-index structure of its own, e.g. reconstructed directly from a
    PCA component space) into a proper indexed Mesh."""
    return _weld(tri_verts, decimals=decimals)


def _weld_indexed(verts: np.ndarray, faces: np.ndarray, decimals: int = 6) -> Mesh:
    """Weld coincident vertices in an already-indexed triangulated mesh."""
    if faces.shape[0] == 0:
        return Mesh(vertices=verts, faces=faces)
    keys = np.round(verts, decimals)
    uniq, inverse = np.unique(keys, axis=0, return_inverse=True)
    new_faces = inverse[faces.reshape(-1)].reshape(-1, 3).astype(np.int32)
    return Mesh(vertices=uniq, faces=new_faces)


# ---------------------------------------------------------------------------
# PLY
# ---------------------------------------------------------------------------

def _read_ply_fh(fh) -> Mesh:
    """Parse PLY (ASCII or binary little/big-endian) from a binary file-like."""
    lines = []
    while True:
        line = fh.readline().decode("ascii", errors="replace").rstrip()
        lines.append(line)
        if line.strip() == "end_header":
            break

    fmt_str = "ascii"
    elements = []
    cur: dict | None = None
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        kw = parts[0]
        if kw == "format":
            fmt_str = parts[1]
        elif kw == "element":
            cur = {"name": parts[1], "count": int(parts[2]), "props": []}
            elements.append(cur)
        elif kw == "property" and cur is not None:
            if parts[1] == "list":
                cur["props"].append({"kind": "list",  "ctype": parts[2],
                                     "dtype": parts[3], "name": parts[4]})
            else:
                cur["props"].append({"kind": "scalar", "dtype": parts[1], "name": parts[2]})

    vert_el = next((e for e in elements if e["name"] == "vertex"), None)
    face_el = next((e for e in elements if e["name"] == "face"),   None)
    if vert_el is None:
        raise ValueError("PLY file has no vertex element")

    prop_names = [p["name"] for p in vert_el["props"]]
    try:
        xi, yi, zi = prop_names.index("x"), prop_names.index("y"), prop_names.index("z")
    except ValueError:
        raise ValueError("PLY vertex element is missing x, y, or z properties")

    ascii_mode = (fmt_str == "ascii")
    endian = ">" if fmt_str == "binary_big_endian" else "<"

    def read_scalar(dtype):
        sc, sz = _PLY_TYPES[dtype]
        (v,) = struct.unpack(endian + sc, fh.read(sz))
        return v

    verts = np.empty((vert_el["count"], 3), dtype=np.float64)
    for i in range(vert_el["count"]):
        if ascii_mode:
            vals = fh.readline().decode().split()
            verts[i] = float(vals[xi]), float(vals[yi]), float(vals[zi])
        else:
            row = []
            for p in vert_el["props"]:
                row.append(read_scalar(p["dtype"]))
            verts[i] = row[xi], row[yi], row[zi]

    vert_idx = next(i for i, e in enumerate(elements) if e["name"] == "vertex")
    for el in elements[vert_idx + 1:]:
        if el["name"] == "face":
            break
        for _ in range(el["count"]):
            if ascii_mode:
                fh.readline()
            else:
                for p in el["props"]:
                    if p["kind"] == "list":
                        n = int(read_scalar(p["ctype"]))
                        _, sz = _PLY_TYPES[p["dtype"]]
                        fh.read(n * sz)
                    else:
                        _, sz = _PLY_TYPES[p["dtype"]]
                        fh.read(sz)

    faces: List[List[int]] = []
    if face_el:
        fp = next((p for p in face_el["props"] if p["kind"] == "list"), None)
        if fp:
            for _ in range(face_el["count"]):
                if ascii_mode:
                    vals = fh.readline().decode().split()
                    n = int(vals[0])
                    idx = [int(vals[j + 1]) for j in range(n)]
                else:
                    n = int(read_scalar(fp["ctype"]))
                    sc, sz = _PLY_TYPES[fp["dtype"]]
                    idx = list(struct.unpack(endian + sc * n, fh.read(sz * n)))
                if n == 3:
                    faces.append(idx)
                elif n >= 4:
                    for j in range(1, n - 1):
                        faces.append([idx[0], idx[j], idx[j + 1]])

    faces_arr = (np.asarray(faces, dtype=np.int32) if faces
                 else np.empty((0, 3), dtype=np.int32))
    return _weld_indexed(verts, faces_arr)


def write_ply(mesh: Mesh, path: str) -> None:
    """Write an indexed mesh as ASCII PLY (triangles only)."""
    tris = _triangulate_faces(mesh.faces)
    with open(path, "w") as fh:
        fh.write("ply\nformat ascii 1.0\n")
        fh.write("element vertex %d\n" % mesh.vertex_count)
        fh.write("property float x\nproperty float y\nproperty float z\n")
        fh.write("element face %d\n" % tris.shape[0])
        fh.write("property list uchar int vertex_indices\n")
        fh.write("end_header\n")
        for v in mesh.vertices:
            fh.write("%.6f %.6f %.6f\n" % (v[0], v[1], v[2]))
        for f in tris:
            fh.write("3 %d %d %d\n" % (f[0], f[1], f[2]))


# ---------------------------------------------------------------------------
# 3MF
# ---------------------------------------------------------------------------

def _read_3mf_fh(fh) -> Mesh:
    """Parse a 3MF archive from any binary file-like object."""
    with zipfile.ZipFile(fh) as zf:
        with zf.open("3D/3dmodel.model") as mf:
            root = ET.parse(mf).getroot()
    all_verts: List[List[float]] = []
    all_tris: List[List[int]] = []
    offset = 0
    for obj in root.iter(f"{{{_3MF_NS}}}object"):
        mesh_el = obj.find(f"{{{_3MF_NS}}}mesh")
        if mesh_el is None:
            continue
        verts = [
            [float(v.get("x")), float(v.get("y")), float(v.get("z"))]
            for v in mesh_el.iter(f"{{{_3MF_NS}}}vertex")
        ]
        tris = [
            [int(t.get("v1")) + offset,
             int(t.get("v2")) + offset,
             int(t.get("v3")) + offset]
            for t in mesh_el.iter(f"{{{_3MF_NS}}}triangle")
        ]
        all_verts.extend(verts)
        all_tris.extend(tris)
        offset += len(verts)
    return _weld_indexed(np.asarray(all_verts, dtype=np.float64),
                         np.asarray(all_tris, dtype=np.int32))


_3MF_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
    '</Types>'
)
_3MF_RELS = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Target="/3D/3dmodel.model" '
    'Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
    '</Relationships>'
)


def write_3mf(mesh: Mesh, path: str) -> None:
    """Write an indexed mesh as a minimal, valid 3MF package (single object,
    triangles only)."""
    tris = _triangulate_faces(mesh.faces)
    verts_xml = "".join(
        '<vertex x="%.6f" y="%.6f" z="%.6f"/>' % (v[0], v[1], v[2])
        for v in mesh.vertices
    )
    tris_xml = "".join(
        '<triangle v1="%d" v2="%d" v3="%d"/>' % (t[0], t[1], t[2])
        for t in tris
    )
    model_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<model unit="millimeter" xmlns="%s">'
        '<resources><object id="1" type="model"><mesh>'
        '<vertices>%s</vertices><triangles>%s</triangles>'
        '</mesh></object></resources>'
        '<build><item objectid="1"/></build>'
        '</model>' % (_3MF_NS, verts_xml, tris_xml)
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _3MF_CONTENT_TYPES)
        zf.writestr("_rels/.rels", _3MF_RELS)
        zf.writestr("3D/3dmodel.model", model_xml)


# ---------------------------------------------------------------------------
# Public dispatch API
# ---------------------------------------------------------------------------

def read_mesh(path: str) -> Mesh:
    lower = path.lower()
    if lower.endswith(".obj"):
        return read_obj(path)
    if lower.endswith(".stl"):
        return read_stl(path)
    if lower.endswith(".3mf"):
        with open(path, "rb") as fh:
            return _read_3mf_fh(fh)
    if lower.endswith(".ply"):
        with open(path, "rb") as fh:
            return _read_ply_fh(fh)
    raise ValueError("Unsupported mesh format: %s (use .obj, .stl, .3mf, or .ply)" % path)


def write_mesh(mesh: Mesh, path: str) -> None:
    """Write a mesh, dispatching on `path`'s extension (symmetric with read_mesh)."""
    lower = path.lower()
    if lower.endswith(".obj"):
        return write_obj(mesh, path)
    if lower.endswith(".stl"):
        return write_stl(mesh, path)
    if lower.endswith(".3mf"):
        return write_3mf(mesh, path)
    if lower.endswith(".ply"):
        return write_ply(mesh, path)
    raise ValueError("Unsupported mesh format: %s (use .obj, .stl, .3mf, or .ply)" % path)


def read_mesh_bytes(data: bytes, ext: str) -> Mesh:
    """Parse a mesh from raw bytes. `ext` must include the dot (e.g. '.obj')."""
    ext = ext.lower()
    if ext == ".obj":
        return _read_obj_fh(io.StringIO(data.decode("utf-8", errors="replace")))
    if ext == ".stl":
        return _read_stl_fh(io.BytesIO(data))
    if ext == ".3mf":
        return _read_3mf_fh(io.BytesIO(data))
    if ext == ".ply":
        return _read_ply_fh(io.BytesIO(data))
    raise ValueError(f"Unsupported format: {ext!r} (use .obj, .stl, .3mf, or .ply)")


# ---------------------------------------------------------------------------
# World-Z alignment (vendored from paradigm/core/align.py)
# ---------------------------------------------------------------------------

_EPS = 1e-9


def _rotation_between(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """3x3 rotation matrix taking unit vector a onto unit vector b, via
    Rodrigues' formula."""
    a = a / (np.linalg.norm(a) + _EPS)
    b = b / (np.linalg.norm(b) + _EPS)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    s = float(np.linalg.norm(v))

    if s < _EPS:
        if c > 0.0:
            return np.eye(3)
        # 180 degrees: rotate about any axis perpendicular to a.
        perp = np.array([1.0, 0.0, 0.0])
        if abs(a[0]) > 0.9:
            perp = np.array([0.0, 1.0, 0.0])
        axis = np.cross(a, perp)
        axis /= np.linalg.norm(axis) + _EPS
        K = _skew(axis)
        return np.eye(3) + 2.0 * (K @ K)

    K = _skew(v / s)
    return np.eye(3) + s * K + (1.0 - c) * (K @ K)


def _skew(v: np.ndarray) -> np.ndarray:
    return np.array([
        [0.0, -v[2], v[1]],
        [v[2], 0.0, -v[0]],
        [-v[1], v[0], 0.0],
    ])


def _pin_axis_sign(axis: np.ndarray, centered_pts: np.ndarray) -> np.ndarray:
    """Make the axis sign deterministic: point toward the longer tail of the
    projected-point distribution (skewness sign, falling back to sum)."""
    proj = centered_pts @ axis
    skew = float(np.mean(proj ** 3))
    if abs(skew) > _EPS:
        return axis if skew >= 0 else -axis
    return axis if proj.sum() >= 0 else -axis


def _ensure_proximal_up(pts: np.ndarray) -> bool:
    """Return True if Z should be flipped so the widest end is at +Z.

    Compares mean cross-sectional radius (sqrt(x^2+y^2)) in the bottom and
    top 20% of the Z-range."""
    z = pts[:, 2]
    z_min, z_max = float(z.min()), float(z.max())
    z_range = z_max - z_min
    if z_range < _EPS:
        return False
    lo_mask = z <= z_min + 0.20 * z_range
    hi_mask = z >= z_max - 0.20 * z_range
    if lo_mask.sum() < 3 or hi_mask.sum() < 3:
        return False
    r_lo = np.sqrt(pts[lo_mask, 0] ** 2 + pts[lo_mask, 1] ** 2).mean()
    r_hi = np.sqrt(pts[hi_mask, 0] ** 2 + pts[hi_mask, 1] ** 2).mean()
    return r_lo > r_hi  # wider end is at -Z -> needs flip


def align_mesh_to_world_z(mesh: Mesh) -> AlignmentResult:
    """PCA-align a mesh's principal axis to world Z, centroid to origin."""
    pts = mesh.vertices
    n = pts.shape[0]
    if n < 3:
        return AlignmentResult(mesh, np.array([0.0, 0.0, 1.0]),
                               np.zeros(3), "Mesh has too few vertices.")

    centroid = pts.mean(axis=0)
    centered = pts - centroid

    cov = (centered.T @ centered) / float(n)

    eigvals, eigvecs = np.linalg.eigh(cov)
    principal_axis = eigvecs[:, -1]  # largest eigenvalue
    principal_axis = principal_axis / (np.linalg.norm(principal_axis) + _EPS)
    principal_axis = _pin_axis_sign(principal_axis, centered)

    world_z = np.array([0.0, 0.0, 1.0])
    R = _rotation_between(principal_axis, world_z)

    aligned_pts = centered @ R.T
    aligned_pts = aligned_pts - aligned_pts.mean(axis=0)

    flipped = _ensure_proximal_up(aligned_pts)
    if flipped:
        aligned_pts[:, 2] *= -1
        faces = mesh.faces[:, ::-1]  # reverse winding after Z reflection
    else:
        faces = mesh.faces

    aligned = Mesh(vertices=aligned_pts, faces=faces)

    flip_note = " Z-axis flipped: proximal (wide) end oriented to +Z." if flipped else ""
    msg = "Aligned mesh axis to world Z and moved centroid to origin." + flip_note
    return AlignmentResult(aligned, principal_axis, centroid, msg)
