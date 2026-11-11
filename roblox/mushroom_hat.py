"""Sample UGC accessory: low-poly mushroom hat. Run: python3 mushroom_hat.py
Outputs mushroom_hat.fbx + mushroom_hat.png next to this file."""
import math, os, random
import bpy, bmesh

OUT = os.path.dirname(os.path.abspath(__file__))
bpy.ops.wm.read_factory_settings(use_empty=True)
random.seed(7)


def mat(name, rgb, rough=0.6):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    return m


RED, CREAM, WHITE = mat("cap", (0.80, 0.08, 0.07)), mat("gill", (0.93, 0.85, 0.70)), mat("spot", (1, 0.97, 0.9))
parts = []

# Cap: top half of a low-res sphere, squashed, with a slightly flared rim
bpy.ops.mesh.primitive_uv_sphere_add(segments=14, ring_count=8, radius=1.0)
cap = bpy.context.object
bm = bmesh.new()
bm.from_mesh(cap.data)
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -0.01], context="VERTS")
bm.to_mesh(cap.data)
bm.free()
for v in cap.data.vertices:
    v.co.z *= 0.75
    if v.co.z < 0.05:  # rim ring: flare out and droop
        v.co.x *= 1.12
        v.co.y *= 1.12
        v.co.z -= 0.12
cap.data.materials.append(RED)
parts.append(cap)

# Underside: shallow cone closing the cap (the gills), opening for the head
bpy.ops.mesh.primitive_cone_add(vertices=14, radius1=1.12, radius2=0.55, depth=0.22, location=(0, 0, -0.01), end_fill_type="NOTHING")
gill = bpy.context.object
gill.rotation_euler.x = math.pi  # wide end up, meeting the rim
gill.data.materials.append(CREAM)
parts.append(gill)

# Spots: flattened low-poly blobs laid on the cap surface
for i in range(7):
    phi = random.uniform(0.25, 1.15)  # angle from the top
    theta = i * 2 * math.pi / 7 + random.uniform(-0.3, 0.3)
    n = (math.sin(phi) * math.cos(theta), math.sin(phi) * math.sin(theta), math.cos(phi))
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=random.uniform(0.13, 0.24), location=(n[0], n[1], n[2] * 0.75))
    s = bpy.context.object
    s.scale.z = 0.3
    s.rotation_euler = (0, phi, theta)  # tilt so the flat side follows the cap
    s.data.materials.append(WHITE)
    parts.append(s)

bpy.ops.object.select_all(action="DESELECT")
for p in parts:
    p.select_set(True)
bpy.context.view_layer.objects.active = cap
bpy.ops.object.join()
hat = bpy.context.object
hat.name = "MushroomHat"
bpy.ops.object.transform_apply(rotation=True, scale=True)

tris = sum(len(p.vertices) - 2 for p in hat.data.polygons)
assert tris <= 4000, f"{tris} tris exceeds Roblox accessory limit"  # Roblox cap for accessories
print(f"triangles: {tris}")

bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, "mushroom_hat.fbx"), use_selection=True)

# Preview render
bpy.ops.object.light_add(type="SUN", rotation=(0.7, 0.2, 0.6))
bpy.context.object.data.energy = 2.5
bpy.ops.object.camera_add(location=(3.2, -3.2, 1.9))
cam = bpy.context.object
cam.rotation_euler = (math.radians(68), 0, math.radians(45))
sc = bpy.context.scene
sc.camera = cam
sc.world = bpy.data.worlds.new("w")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.75, 0.85, 0.95, 1)
sc.view_settings.view_transform = "Standard"
sc.render.engine = "CYCLES"
sc.cycles.samples = 48
sc.render.resolution_x = sc.render.resolution_y = 768
sc.render.filepath = os.path.join(OUT, "mushroom_hat.png")
bpy.ops.render.render(write_still=True)
