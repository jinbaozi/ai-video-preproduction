"""Executed by Blender only. Build, reopen and render a baked AVIR geometry plan."""
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Vector, Matrix
from bpy_extras.object_utils import world_to_camera_view


def convert(v):
    # AVIR screen-right/up/depth -> Blender X/Y/Z. The swap is intentional:
    # preserve AVIR's screen-right basis, not a second camera handedness convention.
    return Vector((v[0], v[2], v[1]))


def restore(v):
    return [v.x, v.z, v.y]


def basis(forward, roll=0):
    f = Vector(forward).normalized(); r = Vector((0,1,0)).cross(f).normalized(); u = f.cross(r)
    a = math.radians(roll)
    return r*math.cos(a)+u*math.sin(a), -r*math.sin(a)+u*math.cos(a), f


def key(obj, name, value, at):
    setattr(obj, name, value); obj.keyframe_insert(data_path=name, frame=at)


def run(plan_path, out):
    plan = json.loads(plan_path.read_text()); out.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene; scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x, scene.render.resolution_y = plan['geometry']['resolution']
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1
    scene.render.fps = plan['fps']; scene.render.fps_base = 1
    scene.render.image_settings.file_format = 'PNG'; scene.render.image_settings.color_mode = 'RGB'
    scene.render.film_transparent = False
    scene.display.shading.light = 'STUDIO'; scene.display.shading.color_type = 'SINGLE'
    scene.display.shading.single_color = (.72,.72,.72)
    scene.display.shading.show_shadows = True; scene.display.shading.show_cavity = True
    scene.display.shading.background_type = 'WORLD'; scene.world.color = (.12,.12,.12)
    scene.view_settings.view_transform = 'Standard'
    scene.frame_start = 1; scene.frame_end = len(plan['video_samples'])
    camera_data = bpy.data.cameras.new('AVIR_CAMERA'); camera = bpy.data.objects.new('AVIR_CAMERA', camera_data)
    scene.collection.objects.link(camera); scene.camera = camera
    camera_data.sensor_fit = 'VERTICAL'; camera_data.sensor_height = 36
    camera_data.clip_start = .001; camera_data.clip_end = 10000; camera_data.dof.use_dof = False
    objects = {}
    for obj in plan['geometry']['objects']:
        if obj['shape'] == 'box': bpy.ops.mesh.primitive_cube_add(size=1)
        elif obj['shape'] == 'ellipsoid': bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=1)
        else: bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=1, depth=1)
        mesh = bpy.context.object; mesh.name = obj['id']; mesh.rotation_mode = 'QUATERNION'
        objects[obj['id']] = mesh
    camera.rotation_mode = 'QUATERNION'
    for sample in plan['samples']:
        at = 1 + (sample['at_ms']-plan['start_ms'])*plan['fps']/1000
        cam = sample['camera']; r,u,f = basis(cam['forward'],cam['roll_deg'])
        key(camera,'location',convert(cam['position']),at)
        key(camera,'rotation_quaternion',Matrix((convert(r),convert(u),-convert(f))).transposed().to_quaternion(),at)
        x,y,w,h = cam['crop']; aspect = cam['output_aspect']
        key(camera_data,'lens',36/(2*math.tan(math.radians(cam['fov'])/2)*h),at)
        key(camera_data,'shift_x',(.5-(.5-x)/w)*aspect,at)
        key(camera_data,'shift_y',((.5-y)/h-.5),at)
        for obj in sample['objects']:
            mesh = objects[obj['id']]
            if obj['shape'] == 'bone':
                start, end = convert(obj['position']), convert(obj['end_position'])
                key(mesh,'location',(start+end)/2,at)
                key(mesh,'rotation_quaternion',(end-start).to_track_quat('Z','Y'),at)
                key(mesh,'scale',(obj['radius'],obj['radius'],(end-start).length),at)
            else:
                key(mesh,'location',convert(obj['position']),at)
                r,u,f = basis(obj.get('forward',[0,0,1]))
                key(mesh,'rotation_quaternion',Matrix((convert(r),convert(f),convert(u))).transposed().to_quaternion(),at)
                size = convert(obj['dimensions'])/(2 if obj['shape'] == 'ellipsoid' else 1)
                key(mesh,'scale',size,at)
    # Bake only declared/evaluated samples. Never add Bezier motion or interpolate pose.
    for owner in [camera, camera_data, *objects.values()]:
        if owner.animation_data and owner.animation_data.action:
            for layer in owner.animation_data.action.layers:
                for strip in layer.strips:
                    for bag in strip.channelbags:
                        for curve in bag.fcurves:
                            for point in curve.keyframe_points: point.interpolation = 'CONSTANT'
    scene['avir_plan_sha_provenance'] = str(plan_path.name)
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene.blend'))
    bpy.ops.wm.open_mainfile(filepath=str(out/'scene.blend'), load_ui=False, use_scripts=False)
    scene = bpy.context.scene; camera = scene.camera
    rows = []; (out/'frames').mkdir(exist_ok=True)
    for index,sample in enumerate(plan['samples']):
        at = 1+(sample['at_ms']-plan['start_ms'])*plan['fps']/1000
        scene.frame_set(math.floor(at), subframe=at-math.floor(at))
        bpy.context.view_layer.update(); deps = bpy.context.evaluated_depsgraph_get()
        objects_read = {}
        for obj in sample['objects']:
            mesh = bpy.data.objects[obj['id']].evaluated_get(deps)
            objects_read[obj['id']] = {'center': restore(mesh.matrix_world.translation),
                'basis_vectors': [restore(mesh.matrix_world.to_3x3() @ Vector(v)) for v in ((1,0,0),(0,1,0),(0,0,1))],
                'vertices': [restore(mesh.matrix_world @ v.co) for v in mesh.data.vertices]}
        projections = {}
        for p in sample['source_points']:
            if p['projection']['xy'] is not None:
                v = world_to_camera_view(scene,camera,convert(p['position']))
                projections[p['id']] = [v.x,1-v.y]
        rows.append({'at_ms':sample['at_ms'], 'objects':objects_read, 'projections':projections,
                     'resolution':[scene.render.resolution_x,scene.render.resolution_y]})
        scene.render.filepath = str(out/f'frames/{index:06d}.png'); bpy.ops.render.render(write_still=True)
    result = {'renderer': {'name':'Blender','version':bpy.app.version_string,'build_hash':bpy.app.build_hash.decode(),
                          'engine':scene.render.engine,'readback':'REOPENED_BLEND'}, 'samples':rows}
    (out/'blender-readback.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,sort_keys=True,indent=2)+'\n')


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--')+1:]; run(Path(args[0]),Path(args[1]))
