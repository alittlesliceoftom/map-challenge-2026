"""Procedural, animated low-poly people as binary glTF (.glb): a cyclist and a walker.

Both are rigid jointed figures animated by node rotations. deck.gl's ScenegraphLayer
plays node animations but never skins a mesh, so a skinned character (CesiumMan) stays
frozen in its bind pose however its animation is driven.

Cyclist: the wheels and crank turn, and the legs follow the pedals by two-bone IK.
One animation cycle (1 s) is one turn of the wheels and the crank.
Walker: one cycle (1 s) is two steps; the body bobs so a foot is always on the ground.

Model space: X forward, Y up (glTF convention), so the page orients it exactly like
the walking figure: getOrientation = [0, 90 - heading, 90].
"""

import json
import math
import struct

import numpy as np

# Geometry (metres)
WHEEL_R = 0.34
FRONT_HUB = (0.55, WHEEL_R)
REAR_HUB = (-0.50, WHEEL_R)
BB = (0.0, 0.30)            # bottom bracket (crank axle)
CRANK_R = 0.17
HIP = (-0.18, 0.98)
THIGH, SHIN = 0.46, 0.46
LEG_Z = 0.11                # legs and pedals either side of the frame
FRAMES = 17                 # animation keyframes over one cycle

COLOURS = {
    "frame": (0.20, 0.73, 0.93, 1), "tyre": (0.10, 0.10, 0.10, 1), "metal": (0.55, 0.55, 0.58, 1),
    "shirt": (1.00, 0.82, 0.40, 1), "legs": (0.22, 0.22, 0.26, 1), "skin": (0.88, 0.70, 0.60, 1),
    "helmet": (0.95, 0.95, 0.95, 1), "hair": (0.25, 0.17, 0.12, 1),
    "red": (0.86, 0.10, 0.12, 1), "white": (0.97, 0.97, 0.97, 1), "jeans": (0.18, 0.32, 0.62, 1),
    "glasses": (0.08, 0.08, 0.08, 1),
    "bus_red": (0.80, 0.06, 0.07, 1), "glass": (0.09, 0.12, 0.16, 1), "roof": (0.86, 0.86, 0.84, 1),
    "skirt": (0.12, 0.12, 0.12, 1), "destination": (1.00, 0.78, 0.18, 1), "lamp": (1.00, 0.97, 0.85, 1),
    "tail": (0.55, 0.02, 0.02, 1),
}

# Walker geometry (metres): about 1.7 m tall
W_THIGH, W_SHIN = 0.44, 0.44
W_TORSO, W_ARM = 0.55, 0.58
W_LEG_Z, W_ARM_Z = 0.09, 0.22
THIGH_SWING, ARM_SWING, KNEE_FLEX = math.radians(24), math.radians(22), math.radians(50)


# ── kinematics ───────────────────────────────────────────────────────────────
def _leg(pedal: np.ndarray) -> tuple[float, float]:
    """Thigh and shin angles (radians, CCW from +X) putting the foot on the pedal,
    knee bent forward."""
    hip = np.array(HIP)
    d = pedal - hip
    dist = min(np.linalg.norm(d), THIGH + SHIN - 1e-6)
    a = math.atan2(d[1], d[0])
    alpha = math.acos((THIGH**2 + dist**2 - SHIN**2) / (2 * THIGH * dist))
    thigh = a + alpha
    knee = hip + THIGH * np.array([math.cos(thigh), math.sin(thigh)])
    e = pedal - knee
    return thigh, math.atan2(e[1], e[0])


def cyclist_pose(theta: float) -> dict:
    """Crank angle theta -> pedal and foot positions plus leg angles, in the XY plane."""
    bb = np.array(BB)
    pose = {"bb": tuple(bb)}
    for side, phase in (("R", 0.0), ("L", math.pi)):
        pedal = bb + CRANK_R * np.array([math.cos(theta + phase), math.sin(theta + phase)])
        thigh, shin = _leg(pedal)
        knee = np.array(HIP) + THIGH * np.array([math.cos(thigh), math.sin(thigh)])
        foot = knee + SHIN * np.array([math.cos(shin), math.sin(shin)])
        pose.update({f"pedal_{side}": tuple(pedal), f"foot_{side}": tuple(foot),
                     f"thigh_{side}": thigh, f"shin_{side}": shin})
    return pose


def walker_pose(phase: float) -> dict:
    """Walk-cycle phase in [0, 1) (two steps) -> joint angles (radians, CCW from +X) and
    hip height, with the hip at x = 0 and the lower foot exactly on the ground."""
    pose, feet = {}, {}
    for side, offset in (("R", 0.0), ("L", 0.5)):
        a = 2 * math.pi * (phase + offset)
        thigh = -math.pi / 2 + THIGH_SWING * math.sin(a)
        shin = thigh - KNEE_FLEX * max(0.0, math.cos(a)) ** 2  # knee folds while the leg swings through
        knee = W_THIGH * np.array([math.cos(thigh), math.sin(thigh)])
        feet[side] = knee + W_SHIN * np.array([math.cos(shin), math.sin(shin)])
        # arms swing against the leg on the same side
        pose.update({"thigh_" + side: thigh, "shin_" + side: shin,
                     "arm_" + side: -math.pi / 2 - ARM_SWING * math.sin(a)})
    hip_y = -min(feet["L"][1], feet["R"][1])
    for side, f in feet.items():
        pose["foot_" + side] = (float(f[0]), float(f[1] + hip_y))
    pose["hip_y"] = hip_y
    return pose


def walker_stride() -> float:
    """Ground covered per animation cycle (two steps), in model metres."""
    span = max(abs(walker_pose(p)["foot_R"][0] - walker_pose(p)["foot_L"][0]) for p in np.linspace(0, 1, 65))
    return 2 * span


# ── meshes ───────────────────────────────────────────────────────────────────
def _box() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Unit cube centred on the origin, flat-shaded (24 vertices)."""
    pos, nrm, idx = [], [], []
    for axis in range(3):
        for sign in (-1, 1):
            n = np.zeros(3); n[axis] = sign
            u, v = np.zeros(3), np.zeros(3)
            u[(axis + 1) % 3] = 0.5; v[(axis + 2) % 3] = 0.5
            c = n * 0.5
            base = len(pos)
            for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                pos.append(c + su * u + sv * v); nrm.append(n)
            quad = [0, 1, 2, 0, 2, 3] if sign > 0 else [0, 2, 1, 0, 3, 2]
            idx += [base + q for q in quad]
    return np.array(pos, "f4"), np.array(nrm, "f4"), np.array(idx, "u2")


def _ring(r_out: float, r_in: float, width: float, seg: int = 24):
    """A tyre: an annulus in the XY plane, extruded along Z."""
    pos, nrm, idx = [], [], []
    ang = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    for z, nz in ((width / 2, 1), (-width / 2, -1)):        # side faces
        base = len(pos)
        for a in ang:
            for r in (r_out, r_in):
                pos.append((r * math.cos(a), r * math.sin(a), z)); nrm.append((0, 0, nz))
        for i in range(seg):
            o0, i0, o1, i1 = (base + 2 * i, base + 2 * i + 1,
                              base + 2 * ((i + 1) % seg), base + 2 * ((i + 1) % seg) + 1)
            idx += [o0, o1, i0, i0, o1, i1] if nz > 0 else [o0, i0, o1, i0, i1, o1]
    for r, s in ((r_out, 1), (r_in, -1)):                   # tread and inner rim
        base = len(pos)
        for a in ang:
            n = (s * math.cos(a), s * math.sin(a), 0)
            for z in (width / 2, -width / 2):
                pos.append((r * math.cos(a), r * math.sin(a), z)); nrm.append(n)
        for i in range(seg):
            a0, b0, a1, b1 = (base + 2 * i, base + 2 * i + 1,
                              base + 2 * ((i + 1) % seg), base + 2 * ((i + 1) % seg) + 1)
            idx += [a0, b0, a1, a1, b0, b1] if s > 0 else [a0, a1, b0, a1, b1, b0]
    return np.array(pos, "f4"), np.array(nrm, "f4"), np.array(idx, "u2")


# ── glTF assembly ────────────────────────────────────────────────────────────
class _Builder:
    def __init__(self):
        self.bin = bytearray()
        self.g = {"asset": {"version": "2.0", "generator": "asliceoftom models.py"},
                  "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [], "meshes": [],
                  "materials": [], "accessors": [], "bufferViews": [], "animations": []}
        self.mat = {}

    def _view(self, arr: np.ndarray, target=None) -> int:
        while len(self.bin) % 4:
            self.bin += b"\0"
        view = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": arr.nbytes}
        if target:
            view["target"] = target
        self.bin += arr.tobytes()
        self.g["bufferViews"].append(view)
        return len(self.g["bufferViews"]) - 1

    def _acc(self, arr: np.ndarray, kind: str, minmax=False, target=None) -> int:
        ctype = {"f4": 5126, "u2": 5123}[arr.dtype.str[1:]]
        acc = {"bufferView": self._view(arr, target), "componentType": ctype,
               "count": len(arr), "type": kind}
        if minmax:
            acc["min"] = arr.min(0).tolist() if arr.ndim > 1 else [float(arr.min())]
            acc["max"] = arr.max(0).tolist() if arr.ndim > 1 else [float(arr.max())]
        self.g["accessors"].append(acc)
        return len(self.g["accessors"]) - 1

    def material(self, name: str) -> int:
        if name not in self.mat:
            self.g["materials"].append({"name": name, "pbrMetallicRoughness": {
                "baseColorFactor": list(COLOURS[name]), "metallicFactor": 0.0, "roughnessFactor": 0.8}})
            self.mat[name] = len(self.g["materials"]) - 1
        return self.mat[name]

    def mesh(self, geom, material: str) -> int:
        pos, nrm, idx = geom
        prim = {"attributes": {"POSITION": self._acc(pos, "VEC3", True, 34962),
                               "NORMAL": self._acc(nrm, "VEC3", target=34962)},
                "indices": self._acc(idx, "SCALAR", target=34963), "material": self.material(material)}
        self.g["meshes"].append({"primitives": [prim]})
        return len(self.g["meshes"]) - 1

    def node(self, name: str, parent: int | None = None, **props) -> int:
        self.g["nodes"].append({"name": name, **props})
        i = len(self.g["nodes"]) - 1
        if parent is not None:
            self.g["nodes"][parent].setdefault("children", []).append(i)
        return i

    def animate(self, node: int, path: str, times: np.ndarray, values: np.ndarray):
        if not self.g["animations"]:
            self.g["animations"].append({"name": "ride", "channels": [], "samplers": []})
        anim = self.g["animations"][0]
        anim["samplers"].append({"input": self._acc(times.astype("f4"), "SCALAR", True),
                                 "output": self._acc(values.astype("f4"), f"VEC{values.shape[1]}"),
                                 "interpolation": "LINEAR"})
        anim["channels"].append({"sampler": len(anim["samplers"]) - 1,
                                 "target": {"node": node, "path": path}})

    def glb(self) -> bytes:
        if not self.g["animations"]:
            del self.g["animations"]
        while len(self.bin) % 4:
            self.bin += b"\0"
        self.g["buffers"] = [{"byteLength": len(self.bin)}]
        js = json.dumps(self.g, separators=(",", ":")).encode()
        js += b" " * (-len(js) % 4)
        total = 12 + 8 + len(js) + 8 + len(self.bin)
        return (struct.pack("<III", 0x46546C67, 2, total)
                + struct.pack("<II", len(js), 0x4E4F534A) + js
                + struct.pack("<II", len(self.bin), 0x004E4942) + bytes(self.bin))


def _qz(angle: float) -> list[float]:
    """Quaternion for a rotation about Z (CCW from +X toward +Y)."""
    return [0.0, 0.0, math.sin(angle / 2), math.cos(angle / 2)]


def _bar(b: _Builder, parent: int, name: str, p0, p1, thick: float, mesh: int, z: float = 0.0):
    """A box spanning p0 -> p1 in the XY plane."""
    (x0, y0), (x1, y1) = p0, p1
    length = math.hypot(x1 - x0, y1 - y0)
    b.node(name, parent, mesh=mesh, translation=[(x0 + x1) / 2, (y0 + y1) / 2, z],
           rotation=_qz(math.atan2(y1 - y0, x1 - x0)), scale=[length, thick, thick])


def _limb(b: _Builder, parent: int, name: str, pivot, length: float, thick: float, mesh: int, z: float):
    """A pivot node (animated) with a box hanging along its local +X."""
    j = b.node(name, parent, translation=[pivot[0], pivot[1], z])
    b.node(name + "_box", j, mesh=mesh, translation=[length / 2, 0, 0], scale=[length, thick, thick])
    return j


def cyclist_glb() -> bytes:
    b = _Builder()
    box, ring = _box(), _ring(WHEEL_R, WHEEL_R - 0.045, 0.04)
    m = {k: b.mesh(box, k) for k in ("frame", "metal", "shirt", "legs", "skin", "helmet")}
    tyre = b.mesh(ring, "tyre")
    root = b.node("cyclist")

    # bike
    seat, head = (-0.13, 0.88), (0.42, 0.86)
    for name, p0, p1 in (("top_tube", seat, head), ("down_tube", head, BB), ("seat_tube", BB, seat),
                         ("fork", head, FRONT_HUB)):
        _bar(b, root, name, p0, p1, 0.04, m["frame"])
    for z in (-0.05, 0.05):
        _bar(b, root, "chain_stay", BB, REAR_HUB, 0.025, m["frame"], z)
        _bar(b, root, "seat_stay", seat, REAR_HUB, 0.025, m["frame"], z)
    b.node("saddle", root, mesh=m["legs"], translation=[seat[0], seat[1] + 0.05, 0], scale=[0.24, 0.05, 0.14])
    b.node("stem", root, mesh=m["metal"], translation=[0.44, 0.94, 0], scale=[0.04, 0.16, 0.04])
    b.node("handlebar", root, mesh=m["metal"], translation=[0.46, 1.01, 0], scale=[0.05, 0.04, 0.50])
    wheels = []
    for name, hub in (("wheel_front", FRONT_HUB), ("wheel_rear", REAR_HUB)):
        w = b.node(name, root, mesh=tyre, translation=[hub[0], hub[1], 0])
        for k in range(3):  # spokes, so the turning shows
            b.node("spoke", w, mesh=m["metal"], rotation=_qz(k * math.pi / 3),
                   scale=[2 * WHEEL_R - 0.06, 0.012, 0.012])
        wheels.append(w)
    crank = b.node("crank", root, translation=[BB[0], BB[1], 0])
    for side, z, phase in (("R", LEG_Z, 0.0), ("L", -LEG_Z, math.pi)):
        c, s = math.cos(phase), math.sin(phase)
        b.node("crank_arm_" + side, crank, mesh=m["metal"], translation=[c * CRANK_R / 2, s * CRANK_R / 2, z],
               rotation=_qz(phase), scale=[CRANK_R, 0.025, 0.02])
        b.node("pedal_" + side, crank, mesh=m["legs"], translation=[c * CRANK_R, s * CRANK_R, z * 1.4],
               scale=[0.10, 0.025, 0.08])

    # rider
    shoulder, hands = (0.24, 1.40), (0.45, 1.03)
    _bar(b, root, "torso", HIP, shoulder, 0.30, m["shirt"])
    b.node("head", root, mesh=m["skin"], translation=[0.33, 1.58, 0], scale=[0.20, 0.22, 0.18])
    b.node("helmet", root, mesh=m["helmet"], translation=[0.32, 1.68, 0], scale=[0.26, 0.09, 0.22])
    for z in (-0.17, 0.17):
        _bar(b, root, "arm", shoulder, hands, 0.08, m["shirt"], z)
    legs = {}
    for side, z in (("R", LEG_Z), ("L", -LEG_Z)):
        thigh = _limb(b, root, "thigh_" + side, HIP, THIGH, 0.14, m["legs"], z)
        shin = b.node("shin_" + side, thigh, translation=[THIGH, 0, 0])
        b.node("shin_box_" + side, shin, mesh=m["legs"], translation=[SHIN / 2, 0, 0], scale=[SHIN, 0.11, 0.11])
        b.node("shoe_" + side, shin, mesh=m["legs"], translation=[SHIN + 0.02, 0, 0], scale=[0.08, 0.06, 0.10])
        legs[side] = (thigh, shin)

    # animation: one wheel and crank turn per second, wheels roll forward (clockwise in XY)
    t = np.linspace(0, 1, FRAMES)
    turn = -2 * math.pi * t
    for w in wheels:
        b.animate(w, "rotation", t, np.array([_qz(a) for a in turn]))
    b.animate(crank, "rotation", t, np.array([_qz(a) for a in turn]))
    poses = [cyclist_pose(a) for a in turn]
    for side, (thigh, shin) in legs.items():
        b.animate(thigh, "rotation", t, np.array([_qz(p["thigh_" + side]) for p in poses]))
        b.animate(shin, "rotation", t, np.array([_qz(p["shin_" + side] - p["thigh_" + side]) for p in poses]))
    return b.glb()


def walker_glb(shirt=(0.93, 0.47, 0.20, 1), striped: bool = False) -> bytes:
    """A walking figure. striped=True dresses them in a red-and-white striped jumper,
    bobble hat, round glasses and blue jeans: one to spot in the crowd."""
    b = _Builder()
    b.mat["shirt"] = len(b.g["materials"])
    b.g["materials"].append({"name": "shirt", "pbrMetallicRoughness": {
        "baseColorFactor": list(COLOURS["red"] if striped else shirt), "metallicFactor": 0.0, "roughnessFactor": 0.8}})
    box = _box()
    m = {k: b.mesh(box, k) for k in ("shirt", "legs", "skin", "hair")}
    if striped:
        m |= {k: b.mesh(box, k) for k in ("red", "white", "jeans", "glasses")}
        m["legs"] = m["jeans"]
    root = b.node("walker")
    body = b.node("body", root, translation=[0, walker_pose(0)["hip_y"], 0])
    if striped:
        n = 8
        for k in range(n):
            b.node(f"stripe_{k}", body, mesh=m["red" if k % 2 else "white"],
                   translation=[0, (k + 0.5) * W_TORSO / n, 0], scale=[0.22, W_TORSO / n, 0.40])
    else:
        b.node("torso", body, mesh=m["shirt"], translation=[0, W_TORSO / 2, 0], scale=[0.22, W_TORSO, 0.40])
    b.node("head", body, mesh=m["skin"], translation=[0.01, W_TORSO + 0.15, 0], scale=[0.20, 0.22, 0.18])
    if striped:
        top = W_TORSO + 0.26
        b.node("hat_band", body, mesh=m["white"], translation=[-0.01, top, 0], scale=[0.22, 0.05, 0.20])
        b.node("hat", body, mesh=m["red"], translation=[-0.01, top + 0.06, 0], scale=[0.18, 0.08, 0.16])
        b.node("bobble", body, mesh=m["white"], translation=[-0.01, top + 0.14, 0], scale=[0.08, 0.08, 0.08])
        for z in (-0.05, 0.05):  # round-ish lenses and a bridge
            b.node("glasses", body, mesh=m["glasses"], translation=[0.115, W_TORSO + 0.17, z], scale=[0.02, 0.06, 0.07])
        b.node("glasses_bridge", body, mesh=m["glasses"], translation=[0.115, W_TORSO + 0.18, 0], scale=[0.02, 0.015, 0.04])
    else:
        b.node("hair", body, mesh=m["hair"], translation=[-0.02, W_TORSO + 0.25, 0], scale=[0.20, 0.07, 0.19])
    joints = {}
    for side, z in (("R", W_LEG_Z), ("L", -W_LEG_Z)):
        thigh = _limb(b, body, "thigh_" + side, (0, 0), W_THIGH, 0.15, m["legs"], z)
        shin = b.node("shin_" + side, thigh, translation=[W_THIGH, 0, 0])
        b.node("shin_box_" + side, shin, mesh=m["legs"], translation=[W_SHIN / 2, 0, 0], scale=[W_SHIN, 0.12, 0.12])
        b.node("shoe_" + side, shin, mesh=m["hair"], translation=[W_SHIN, 0.05, 0], scale=[0.06, 0.24, 0.11])
        joints["thigh_" + side], joints["shin_" + side] = thigh, shin
    for side, z in (("R", W_ARM_Z), ("L", -W_ARM_Z)):
        arm = _limb(b, body, "arm_" + side, (0, W_TORSO - 0.06), W_ARM - 0.1, 0.09, m["shirt"], z)
        b.node("hand_" + side, arm, mesh=m["skin"], translation=[W_ARM - 0.06, 0, 0], scale=[0.09, 0.08, 0.08])
        joints["arm_" + side] = arm

    t = np.linspace(0, 1, FRAMES)
    poses = [walker_pose(p) for p in t]
    b.animate(body, "translation", t, np.array([[0, p["hip_y"], 0] for p in poses]))
    for name, node in joints.items():
        if name.startswith("shin"):
            thigh = "thigh" + name[4:]
            vals = [_qz(p[name] - p[thigh]) for p in poses]
        else:
            vals = [_qz(p[name]) for p in poses]
        b.animate(node, "rotation", t, np.array(vals))
    return b.glb()


def bus_glb() -> bytes:
    """A static low-poly red double-decker, 11 m x 2.5 m x 4.4 m, front at +X.
    +Z is the offside (right), so the doors are on -Z for UK kerbside boarding."""
    b = _Builder()
    box = _box()
    m = {k: b.mesh(box, k) for k in ("bus_red", "glass", "roof", "skirt", "destination", "lamp", "tail", "metal")}
    b.g["materials"][b.mat["glass"]]["pbrMetallicRoughness"].update(metallicFactor=0.3, roughnessFactor=0.25)
    tyre = b.mesh(_ring(0.5, 0.30, 0.30), "tyre")
    root = b.node("bus")
    L, W = 11.0, 2.5

    def part(name, mesh, x0, x1, y0, y1, w):
        b.node(name, root, mesh=m[mesh], translation=[(x0 + x1) / 2, (y0 + y1) / 2, 0],
               scale=[x1 - x0, y1 - y0, w])

    def side(name, mesh, x0, x1, y0, y1, z):
        b.node(name, root, mesh=m[mesh], translation=[(x0 + x1) / 2, (y0 + y1) / 2, z],
               scale=[x1 - x0, y1 - y0, 0.04])

    part("body", "bus_red", -L / 2, L / 2, 0.35, 4.30, W)
    part("skirt", "skirt", -L / 2 - 0.02, L / 2 + 0.02, 0.30, 0.55, W + 0.02)
    part("roof", "roof", -L / 2 + 0.1, L / 2 - 0.1, 4.30, 4.40, W - 0.1)
    # window bands run round the ends too, broken up by red pillars
    part("lower_windows", "glass", -L / 2 - 0.02, L / 2 + 0.02, 1.25, 2.15, W + 0.04)
    part("upper_windows", "glass", -L / 2 - 0.02, L / 2 + 0.02, 2.75, 3.80, W + 0.04)
    for x in np.arange(-L / 2 + 1.4, L / 2 - 0.6, 1.45):
        part("pillar", "bus_red", x - 0.07, x + 0.07, 1.25, 2.15, W + 0.08)
        part("pillar", "bus_red", x - 0.07, x + 0.07, 2.75, 3.80, W + 0.08)
    # front: tall windscreen, destination blind between the decks, headlights
    part("windscreen", "glass", L / 2 - 0.02, L / 2 + 0.04, 0.95, 2.15, W - 0.25)
    part("destination", "destination", L / 2 - 0.02, L / 2 + 0.05, 2.30, 2.60, 1.60)
    for z in (-0.95, 0.95):
        b.node("headlight", root, mesh=m["lamp"], translation=[L / 2 + 0.03, 0.72, z], scale=[0.04, 0.16, 0.30])
        b.node("taillight", root, mesh=m["tail"], translation=[-L / 2 - 0.03, 0.80, z], scale=[0.04, 0.30, 0.20])
    # nearside doors: front (by the driver) and middle
    for x0, x1 in ((3.55, 4.65), (-0.55, 0.55)):
        side("door", "glass", x0, x1, 0.45, 2.15, -W / 2 - 0.03)
    # wheels (rings, so unscaled) with hubs
    for x in (3.85, -2.95):
        for z in (-W / 2 + 0.16, W / 2 - 0.16):
            b.node("wheel", root, mesh=tyre, translation=[x, 0.5, z])
            b.node("hub", root, mesh=m["metal"], translation=[x, 0.5, z], scale=[0.42, 0.42, 0.32])
    return b.glb()


# ── packing artist models (Quaternius Stylized Nature MegaKit, CC0) ───────────
def _tex_refs(material: dict):
    pbr = material.get("pbrMetallicRoughness", {})
    for holder, key in ((pbr, "baseColorTexture"), (pbr, "metallicRoughnessTexture"),
                        (material, "emissiveTexture"), (material, "occlusionTexture")):
        if key in holder:
            yield holder[key]


def pack_gltf(path, max_texture: int = 512) -> bytes:
    """A .gltf + .bin + PNG textures -> one compact .glb for embedding in the page:
    drops tangents and normal maps (unused by deck's simple PBR), keeps only the data
    still referenced, and shrinks textures (JPEG unless the texture needs alpha)."""
    import io
    from pathlib import Path

    from PIL import Image

    path = Path(path)
    g = json.loads(path.read_text())
    bufs = [(path.parent / b["uri"]).read_bytes() for b in g["buffers"]]
    for mesh in g["meshes"]:
        for prim in mesh["primitives"]:
            prim["attributes"].pop("TANGENT", None)
    for mat in g.get("materials", []):
        mat.pop("normalTexture", None)

    # accessors still referenced, renumbered
    used = []
    def keep(i):
        if i not in used:
            used.append(i)
        return used.index(i)
    for mesh in g["meshes"]:
        for prim in mesh["primitives"]:
            prim["attributes"] = {k: keep(v) for k, v in prim["attributes"].items()}
            if "indices" in prim:
                prim["indices"] = keep(prim["indices"])
    for anim in g.get("animations", []):
        for smp in anim["samplers"]:
            smp["input"], smp["output"] = keep(smp["input"]), keep(smp["output"])
    for skin in g.get("skins", []):
        if "inverseBindMatrices" in skin:
            skin["inverseBindMatrices"] = keep(skin["inverseBindMatrices"])

    out = bytearray()
    views, accessors, view_map = [], [], {}
    def add_view(data: bytes, extra=None) -> int:
        while len(out) % 4:
            out.append(0)
        views.append({"buffer": 0, "byteOffset": len(out), "byteLength": len(data), **(extra or {})})
        out.extend(data)
        return len(views) - 1
    for old in used:
        acc = dict(g["accessors"][old])
        v = acc["bufferView"]
        if v not in view_map:
            bv = g["bufferViews"][v]
            start = bv.get("byteOffset", 0)
            extra = {k: bv[k] for k in ("byteStride", "target") if k in bv}
            view_map[v] = add_view(bufs[bv.get("buffer", 0)][start:start + bv["byteLength"]], extra)
        acc["bufferView"] = view_map[v]
        accessors.append(acc)

    # textures still referenced, images shrunk and embedded
    tex_used = sorted({ref["index"] for m in g.get("materials", []) for ref in _tex_refs(m)})
    images, textures = [], []
    for new, old in enumerate(tex_used):
        tex = dict(g["textures"][old])
        im = Image.open(path.parent / g["images"][tex["source"]]["uri"])
        im.thumbnail((max_texture, max_texture))
        buf = io.BytesIO()
        if im.mode in ("RGBA", "LA") and im.getchannel("A").getextrema()[0] < 255:
            im.save(buf, "PNG", optimize=True); mime = "image/png"
        else:
            im.convert("RGB").save(buf, "JPEG", quality=85); mime = "image/jpeg"
        images.append({"bufferView": add_view(buf.getvalue()), "mimeType": mime})
        tex["source"] = new
        textures.append(tex)
    for m in g.get("materials", []):
        for ref in _tex_refs(m):
            ref["index"] = tex_used.index(ref["index"])

    g.update(accessors=accessors, bufferViews=views, images=images, textures=textures)
    if not textures:
        for k in ("images", "textures", "samplers"):
            g.pop(k, None)
    while len(out) % 4:
        out.append(0)
    g["buffers"] = [{"byteLength": len(out)}]
    js = json.dumps(g, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(out)
    return (struct.pack("<III", 0x46546C67, 2, total)
            + struct.pack("<II", len(js), 0x4E4F534A) + js
            + struct.pack("<II", len(out), 0x004E4942) + bytes(out))


# Which MegaKit models go on the bridge, and their texture size (px).
GREENERY = {"CommonTree_3": 512, "CommonTree_5": 512, "Bush_Common_Flowers": 256,
            "Flower_4_Group": 256, "Plant_7_Big": 256}

if __name__ == "__main__":
    # Re-pack the committed models/ from the MegaKit download (data/megakit, git-ignored):
    # https://quaternius.itch.io/stylized-nature-megakit
    from pathlib import Path
    here = Path(__file__).parent
    for name, px in GREENERY.items():
        out = here / "models" / f"{name}.glb"
        out.write_bytes(pack_gltf(here / "data" / "megakit" / "glTF" / f"{name}.gltf", max_texture=px))
        print(f"Saved {out} ({out.stat().st_size / 1e3:.0f} kB)")
