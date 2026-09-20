"""Executed only inside Blender. Input contains already evaluated Canonical frames."""
import json
import sys
from pathlib import Path


def main():
    import bpy
    from mathutils import Vector, Matrix
    from bpy_extras.object_utils import world_to_camera_view

    args = sys.argv[sys.argv.index('--') + 1:]
    payload = json.loads(Path(args[0]).read_text())
    output = Path(args[1])
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'OBJECT'
    scene.render.resolution_x, scene.render.resolution_y = payload['size']
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.fps = payload['fps']
    scene.frame_end = len(payload['frames'])
    objects = {}
    def xyz(value):
        return tuple(value[a] for a in 'xyz')
    def sphere(name, radius, color):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=6, radius=radius)
        result = bpy.context.object
        result.name, result.color = name, color
        return result
    palette = [(0.16, 0.47, 0.85, 1), (0.85, 0.27, 0.17, 1), (0.3, 0.7, 0.3, 1)]
    for index, entity in enumerate(payload['frames'][0]['characters']):
        actor = sphere(entity['character_id'], 0.3, palette[index % len(palette)])
        actor.scale = (0.75, 0.55, 1.35)
        objects[entity['character_id']] = actor
        for name, radius in [('head', .17), ('nose', .06)]:
            objects[entity['character_id'] + ':' + name] = sphere(entity['character_id'] + ':' + name, radius, palette[index % len(palette)])
    for prop in payload['frames'][0]['props']:
        bpy.ops.mesh.primitive_cube_add(size=1)
        objects[prop['asset_id']] = bpy.context.object
        objects[prop['asset_id']].dimensions = (.22, .02, .15)
        objects[prop['asset_id']].color = (.85, .7, .25, 1)
    for fixed in payload['fixed_geometry']:
        bpy.ops.mesh.primitive_cube_add(size=1, location=xyz(fixed['position']))
        cube = bpy.context.object
        cube.name = fixed['element_id']
        cube.dimensions = xyz(fixed['size_m'])
        cube.color = (0.3, 0.3, 0.32, 1)
    camera_data = bpy.data.cameras.new('CanonicalCamera')
    camera = bpy.data.objects.new('CanonicalCamera', camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    readback = {'blender_version': bpy.app.version_string, 'frames': [], 'proxy_dimensions': 'default radius .3m, height 1.5m; not anatomical acceptance'}
    for index, frame in enumerate(payload['frames']):
        scene.frame_set(index + 1)
        state = frame['camera']
        camera.location = xyz(state['position'])
        forward = (Vector(xyz(state['target'])) - camera.location).normalized()
        up_hint = Vector(xyz(state.get('up', {'x': 0, 'y': 0, 'z': 1})))
        right = forward.cross(up_hint).normalized()
        up = right.cross(forward)
        camera.rotation_euler = Matrix((right, up, -forward)).transposed().to_euler()
        camera_data.type = 'ORTHO' if state['projection'] == 'orthographic' else 'PERSP'
        camera_data.lens = state['focal_length_mm']
        camera_data.sensor_width = state['sensor_width_mm']
        camera_data.sensor_fit = 'HORIZONTAL'
        if camera_data.type == 'ORTHO':
            camera_data.ortho_scale = state['ortho_scale_m']
        if state.get('focus_distance_m'):
            camera_data.dof.focus_distance = state['focus_distance_m']
        camera.keyframe_insert('location')
        camera.keyframe_insert('rotation_euler')
        camera_data.keyframe_insert('lens')
        points = []
        for entity in frame['characters']:
            actor = objects[entity['character_id']]
            actor.location = xyz(entity['position'])
            actor.location.z += 1.03
            actor.rotation_mode = 'QUATERNION'
            actor.rotation_quaternion = entity['rotation_quaternion']
            actor.hide_render = not entity['visible']
            actor.keyframe_insert('location')
            actor.keyframe_insert('rotation_quaternion')
            actor.keyframe_insert('hide_render')
            feet = Vector(xyz(entity['position']))
            joints = {'head': feet + Vector((0, 0, 1.6)),
                      'left_shoulder': feet + Vector((-.22, 0, 1.35)), 'right_shoulder': feet + Vector((.22, 0, 1.35)),
                      'left_hand': feet + Vector((-.3, 0, .8)), 'right_hand': feet + Vector((.3, 0, .8)),
                      'left_hip': feet + Vector((-.13, 0, .8)), 'right_hip': feet + Vector((.13, 0, .8)),
                      'left_foot': feet + Vector((-.15, 0, .08)), 'right_foot': feet + Vector((.15, 0, .08))}
            joints = {name: feet + actor.rotation_quaternion @ (position-feet) for name, position in joints.items()}
            joints.update({name: Vector(xyz(target)) for name, target in entity.get('joint_targets', {}).items()})
            objects[entity['character_id'] + ':head'].location = joints['head']
            objects[entity['character_id'] + ':nose'].location = joints['head'] + actor.rotation_quaternion @ Vector((0, -.17, 0))
            for name in ('head', 'nose'):
                objects[entity['character_id'] + ':' + name].hide_render = not entity['visible']
                objects[entity['character_id'] + ':' + name].keyframe_insert('location')
                objects[entity['character_id'] + ':' + name].keyframe_insert('hide_render')
            for start, end in [('left_shoulder', 'left_hand'), ('right_shoulder', 'right_hand'),
                               ('left_hip', 'left_foot'), ('right_hip', 'right_foot')]:
                name = entity['character_id'] + ':' + start + '-' + end
                if name not in objects:
                    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=.075, depth=1)
                    objects[name] = bpy.context.object
                    objects[name].color = actor.color
                bone = objects[name]
                delta = joints[end] - joints[start]
                bone.location = (joints[start] + joints[end])/2
                bone.rotation_euler = delta.to_track_quat('Z', 'Y').to_euler()
                bone.scale.z = max(delta.length, .001)
                bone.hide_render = not entity['visible']
                for field in ('location', 'rotation_euler', 'scale', 'hide_render'):
                    bone.keyframe_insert(field)
            for joint, target in entity.get('joint_targets', {}).items():
                name = entity['character_id'] + ':' + joint
                if name not in objects:
                    objects[name] = sphere(name, 0.05, actor.color)
                objects[name].location = xyz(target)
                objects[name].hide_render = not entity['visible']
                objects[name].keyframe_insert('location')
                objects[name].keyframe_insert('hide_render')
            bpy.context.view_layer.update()
            evaluated_root = actor.matrix_world.translation - Vector((0, 0, 1.03))
            projection = world_to_camera_view(scene, camera, evaluated_root)
            points.append({'character_id': entity['character_id'], 'position': list(evaluated_root),
                           'rotation_quaternion': list(actor.rotation_quaternion),
                           'projection': list(projection), 'visible': entity['visible']})
        for prop in frame['props']:
            objects[prop['asset_id']].location = xyz(prop['position'])
            objects[prop['asset_id']].keyframe_insert('location')
        bpy.context.view_layer.update()
        scene.render.filepath = str(output / f'{index:04d}.png')
        bpy.ops.render.render(write_still=True)
        readback['frames'].append({'time_s': frame['time_s'], 'characters': points,
                                   'camera_matrix': [list(row) for row in camera.matrix_world]})
    bpy.ops.wm.save_as_mainfile(filepath=str(output / 'scene.blend'))
    (output / 'readback.json').write_text(json.dumps(readback, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
