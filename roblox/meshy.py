"""Prompt -> Meshy textured model -> Roblox-ready FBX.
Usage: python3 meshy.py "low poly red mushroom hat, cute, game asset" mushroom_hat
Outputs out/<name>/: <name>.glb (raw), <name>.fbx (<=4000 tris), <name>_thumb.png
Auth: the session proxy injects the Meshy key; elsewhere set MESHY_API_KEY."""
import json, os, ssl, sys, time, urllib.request

API = "https://api.meshy.ai/openapi/v2/text-to-3d"
KEY = os.environ.get("MESHY_API_KEY", "proxy-injected")
MAX_TRIS = 4000  # Roblox accessory triangle limit
CTX = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or ("/root/.ccr/ca-bundle.crt" if os.path.exists("/root/.ccr/ca-bundle.crt") else None))


def call(url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, context=CTX, timeout=60) as r:
        return json.load(r)


def run_task(body):
    task_id = call(API, body)["result"]
    while True:
        t = call(f"{API}/{task_id}")
        print(f"  {body['mode']}: {t['status']} {t.get('progress', 0)}%", flush=True)
        if t["status"] == "SUCCEEDED":
            return t
        if t["status"] in ("FAILED", "CANCELED", "EXPIRED"):
            sys.exit(f"{body['mode']} failed: {t.get('task_error')}")
        time.sleep(10)


def download(url, path):
    with urllib.request.urlopen(url, context=CTX, timeout=120) as r, open(path, "wb") as f:
        f.write(r.read())


def to_roblox_fbx(glb, fbx):
    import bpy  # imported late so the API half runs without Blender
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=glb)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.object
    tris = lambda: sum(len(p.vertices) - 2 for p in obj.data.polygons)
    if tris() > MAX_TRIS:
        mod = obj.modifiers.new("dec", "DECIMATE")
        mod.ratio = MAX_TRIS / tris() * 0.95
        bpy.ops.object.modifier_apply(modifier=mod.name)
    assert tris() <= MAX_TRIS, f"{tris()} tris still over {MAX_TRIS}"
    bpy.ops.export_scene.fbx(filepath=fbx, use_selection=True, path_mode="COPY", embed_textures=True)
    return tris()


if __name__ == "__main__":
    prompt, name = sys.argv[1], sys.argv[2]
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", name)
    os.makedirs(out, exist_ok=True)
    preview = run_task({"mode": "preview", "prompt": prompt, "art_style": "realistic",
                        "should_remesh": True, "topology": "triangle", "target_polycount": 3000})
    refined = run_task({"mode": "refine", "preview_task_id": preview["id"], "enable_pbr": False})
    glb = os.path.join(out, f"{name}.glb")
    download(refined["model_urls"]["glb"], glb)
    download(refined["thumbnail_url"], os.path.join(out, f"{name}_thumb.png"))
    print(f"done: {to_roblox_fbx(glb, os.path.join(out, name + '.fbx'))} tris -> {out}")
