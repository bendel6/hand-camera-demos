"""Minimal GLB writer (numpy -> glTF 2.0 binary) with named nodes, meshes and PBR materials."""
import json, struct
import numpy as np

_CT = {np.dtype(np.float32): 5126, np.dtype(np.uint32): 5125, np.dtype(np.uint16): 5123, np.dtype(np.uint8): 5121}
_TYPE = {1: "SCALAR", 2: "VEC2", 3: "VEC3", 4: "VEC4"}


class GLB:
    def __init__(self):
        self.gltf = {"asset": {"version": "2.0", "generator": "tower-pitch build_context.py"},
                     "scenes": [{"nodes": []}], "scene": 0, "nodes": [], "meshes": [],
                     "materials": [], "accessors": [], "bufferViews": [], "buffers": []}
        self.blob = bytearray()
        self._mat = {}

    def _view(self, arr, target=None):
        while len(self.blob) % 4:
            self.blob.append(0)
        off = len(self.blob)
        self.blob += arr.tobytes()
        v = {"buffer": 0, "byteOffset": off, "byteLength": arr.nbytes}
        if target:
            v["target"] = target
        self.gltf["bufferViews"].append(v)
        return len(self.gltf["bufferViews"]) - 1

    def _acc(self, arr, target=None, normalized=False, minmax=False):
        arr = np.ascontiguousarray(arr)
        comps = 1 if arr.ndim == 1 else arr.shape[1]
        a = {"bufferView": self._view(arr, target), "componentType": _CT[arr.dtype],
             "count": int(arr.shape[0]), "type": _TYPE[comps]}
        if normalized:
            a["normalized"] = True
        if minmax:
            a["min"] = arr.min(axis=0).astype(float).tolist()
            a["max"] = arr.max(axis=0).astype(float).tolist()
        self.gltf["accessors"].append(a)
        return len(self.gltf["accessors"]) - 1

    def material(self, name, color=(1, 1, 1, 1), roughness=0.9, metallic=0.0, double_sided=False):
        if name not in self._mat:
            m = {"name": name, "pbrMetallicRoughness": {"baseColorFactor": list(color),
                 "metallicFactor": metallic, "roughnessFactor": roughness}}
            if double_sided:
                m["doubleSided"] = True
            self.gltf["materials"].append(m)
            self._mat[name] = len(self.gltf["materials"]) - 1
        return self._mat[name]

    def add_mesh_node(self, name, pos, idx, material, normals=None, colors=None, uvs=None, parent=None, extras=None):
        attrs = {"POSITION": self._acc(pos.astype(np.float32), 34962, minmax=True)}
        if normals is not None:
            attrs["NORMAL"] = self._acc(normals.astype(np.float32), 34962)
        if colors is not None:
            attrs["COLOR_0"] = self._acc(colors.astype(np.uint8), 34962, normalized=True)
        if uvs is not None:
            attrs["TEXCOORD_0"] = self._acc(uvs.astype(np.float32), 34962)
        ind = self._acc(idx.astype(np.uint32).ravel(), 34963)
        self.gltf["meshes"].append({"name": name, "primitives": [{"attributes": attrs, "indices": ind,
                                                                   "material": material, "mode": 4}]})
        node = {"name": name, "mesh": len(self.gltf["meshes"]) - 1}
        if extras:
            node["extras"] = extras
        return self._node(node, parent)

    def add_group(self, name, parent=None, extras=None):
        node = {"name": name, "children": []}
        if extras:
            node["extras"] = extras
        return self._node(node, parent)

    def _node(self, node, parent):
        self.gltf["nodes"].append(node)
        i = len(self.gltf["nodes"]) - 1
        if parent is None:
            self.gltf["scenes"][0]["nodes"].append(i)
        else:
            self.gltf["nodes"][parent].setdefault("children", []).append(i)
        return i

    def save(self, path):
        while len(self.blob) % 4:
            self.blob.append(0)
        self.gltf["buffers"] = [{"byteLength": len(self.blob)}]
        js = json.dumps(self.gltf, separators=(",", ":")).encode()
        js += b" " * ((4 - len(js) % 4) % 4)
        total = 12 + 8 + len(js) + 8 + len(self.blob)
        with open(path, "wb") as f:
            f.write(struct.pack("<III", 0x46546C67, 2, total))
            f.write(struct.pack("<II", len(js), 0x4E4F534A)); f.write(js)
            f.write(struct.pack("<II", len(self.blob), 0x004E4942)); f.write(self.blob)
        return total
