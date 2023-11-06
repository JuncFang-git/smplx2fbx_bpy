# -*- coding: utf-8 -*-

# Max-Planck-Gesellschaft zur Förderung der Wissenschaften e.V. (MPG) is
# holder of all proprietary rights on this computer program.
# You can only use this computer program if you have closed
# a license agreement with MPG or you get the right to use the computer
# program from someone who is authorized to grant you that right.
# Any use of the computer program without a valid license is prohibited and
# liable to prosecution.
#
# Copyright©2019 Max-Planck-Gesellschaft zur Förderung
# der Wissenschaften e.V. (MPG). acting on behalf of its Max Planck Institute
# for Intelligent Systems. All rights reserved.
#
# Contact: ps-license@tuebingen.mpg.de
#
# Author: Joachim Tesch, Max Planck Institute for Intelligent Systems, Perceiving Systems
#
# Create keyframed animated skinned SMPL mesh from .pkl pose description
#
# Generated mesh will be exported in FBX or glTF format
#
# Notes:
#  + Male and female gender models only
#  + Script can be run from command line or in Blender Editor (Text Editor>Run Script)
#  + Command line: Install mathutils module in your bpy virtualenv with 'pip install mathutils==2.81.2'

import os
import sys
import bpy
import time
import argparse
import numpy as np
from math import radians
from mathutils import Matrix, Vector, Quaternion, Euler
# import addon_utils


# bone root name of fbx blender 
ROOT_NAME = 'SMPLX-neutral'
# ROOT_NAME = 'Armature'

BODY_JOINT_NAMES = [
    'pelvis',
    'left_hip',
    'right_hip',
    'spine1',
    'left_knee',
    'right_knee',
    'spine2',
    'left_ankle',
    'right_ankle',
    'spine3',
    'left_foot',
    'right_foot',
    'neck',
    'left_collar',
    'right_collar',
    'head',
    'left_shoulder',
    'right_shoulder',
    'left_elbow',
    'right_elbow',
    'left_wrist',
    'right_wrist'
]

LHAND_JOINT_NAMES = [
    'left_index1',
    'left_index2',
    'left_index3',
    'left_middle1',
    'left_middle2',
    'left_middle3',
    'left_pinky1',
    'left_pinky2',
    'left_pinky3',
    'left_ring1',
    'left_ring2',
    'left_ring3',
    'left_thumb1',
    'left_thumb2',
    'left_thumb3',    
]

RHAND_JOINT_NAMES = [
    'right_index1',
    'right_index2',
    'right_index3',
    'right_middle1',
    'right_middle2',
    'right_middle3',
    'right_pinky1',
    'right_pinky2',
    'right_pinky3',
    'right_ring1',
    'right_ring2',
    'right_ring3',
    'right_thumb1',
    'right_thumb2',
    'right_thumb3',
]
# Helper functions

# Computes rotation matrix through Rodrigues formula as in cv2.Rodrigues
# Source: smpl/plugins/blender/corrective_bpy_sh.py
def Rodrigues(rotvec):
    theta = np.linalg.norm(rotvec)
    r = (rotvec/theta).reshape(3, 1) if theta > 0. else rotvec
    cost = np.cos(theta)
    mat = np.asarray([[0, -r[2], r[1]],
                      [r[2], 0, -r[0]],
                      [-r[1], r[0], 0]])
    return(cost*np.eye(3) + (1-cost)*r.dot(r.T) + np.sin(theta)*mat)

def ToQuaternion(rotvec):
    assert(rotvec.shape[-1] == 3 and len(rotvec.shape) <= 2,
           f"Need a a rotvec shape as (N, 3) or (3,) but got {rotvec.shape}")
    if len(rotvec.shape) == 1:
        return np.array(Matrix(Rodrigues(rotvec)).to_quaternion())
    else:
        res = []
        for i in range(rotvec.shape[0]):
            res.append(Matrix(Rodrigues(rotvec[i])).to_quaternion())
        return np.stack(res, axis=0)
    
def get_input_data(input_dir):
    frame_list = sorted(os.listdir(input_path))
    poses, lhposes, rhposes, trans = [], [], [], []
    for file_name in frame_list:
        file_path = os.path.join(input_dir, file_name)
        npz_data = np.load(file_path)
        data = {}
        fix_coor = np.array([[1, 0, 0],
                            [0, 1, 0],
                            [0, 0, -1]], dtype=np.float32)
        # body
        rot= np.concatenate([
            ToQuaternion(npz_data['global_orient']),
            ToQuaternion(npz_data['body_pose'])], axis=0)
        poses.append(rot.flatten())
        # hand
        lhand_quaternions = ToQuaternion(np.matmul(npz_data['left_hand_pose'], fix_coor))
        lhposes.append(lhand_quaternions.reshape(-1, 4))
        
        rhand_quaternions = ToQuaternion(np.matmul(npz_data['right_hand_pose'], fix_coor))
        rhposes.append(rhand_quaternions.reshape(-1, 4))
        
        # trans
        trans.append(npz_data['transl'].reshape(3))
    poses = np.vstack(poses)
    lhposes = np.stack(lhposes)
    rhposes = np.stack(rhposes)
    trans = np.stack(trans)
    return poses, lhposes, rhposes, trans

# Setup scene
def setup_scene(model_path, fps_target):
    scene = bpy.data.scenes['Scene']

    ###########################
    # Engine independent setup
    ###########################

    scene.render.fps = fps_target

    # Remove default cube
    if 'Cube' in bpy.data.objects:
        bpy.data.objects['Cube'].select_set(True)
        bpy.ops.object.delete()

    # Import gender specific .fbx template file
    bpy.ops.import_scene.fbx(filepath=model_path)


# Process single pose into keyframed bone orientations
def process_pose(current_frame, pose, lhandpose, rhandpose, trans, pelvis_position):

    rod_rots = pose.reshape(22, 4)
    lhrod_rots = lhandpose.reshape(15, 4)
    rhrod_rots = rhandpose.reshape(15, 4)
        

    # Set the location of the Pelvis bone to the translation parameter
    armature = bpy.data.objects[ROOT_NAME]
    bones = armature.pose.bones

    # Pelvis: X-Right, Y-Up, Z-Forward (Blender -Y)

    # Set absolute pelvis location relative to Pelvis bone head
    # bones[BODY_JOINT_NAMES[0]].location = Vector((100*trans[1], 100*trans[2], 100*trans[0])) - pelvis_position
    # bones[BODY_JOINT_NAMES[0]].location = Vector((trans[0],trans[1],trans[2])) - pelvis_position
    # bones[BODY_JOINT_NAMES[0]].location = Vector((1, 1, 0)) - pelvis_position
    bones[BODY_JOINT_NAMES[0]].location = Vector((trans[0],trans[1],0)) - pelvis_position

    # bones['Root'].location = Vector(trans)
    bones[BODY_JOINT_NAMES[0]].keyframe_insert('location', frame=current_frame)

    for index, mat_rot in enumerate(rod_rots, 0):
        # if index >= 24:
        if index >= 22:
            continue

        bone = bones[BODY_JOINT_NAMES[index]]

        # bone_rotation = Matrix(mat_rot).to_quaternion()
        bone_rotation = Quaternion(mat_rot)
        quat_x_180_cw = Quaternion((1.0, 0.0, 0.0), radians(-180))

        if index == 0:
            # Rotate pelvis so that avatar stands upright and looks along negative Y avis
            bone.rotation_quaternion = quat_x_180_cw @ bone_rotation
            # bone.rotation_quaternion = (quat_x_90_cw @ quat_z_90_cw) @ bone_rotation
        else:
            bone.rotation_quaternion = bone_rotation

        bone.keyframe_insert('rotation_quaternion', frame=current_frame)

    for index, mat_rot in enumerate(lhrod_rots, 0):
        if index >= 15:
            continue
        bone = bones[LHAND_JOINT_NAMES[index]]
        bone_rotation = Quaternion(mat_rot)
        bone.rotation_quaternion = bone_rotation
        # bone.rotation_quaternion = (quat_x_90_cw @ quat_z_90_cw) @ bone_rotation
        bone.keyframe_insert('rotation_quaternion', frame=current_frame)

    for index, mat_rot in enumerate(rhrod_rots, 0):
        if index >= 15:
            continue
        bone = bones[RHAND_JOINT_NAMES[index]]
        bone_rotation = Quaternion(mat_rot)
        bone.rotation_quaternion = bone_rotation
        bone.keyframe_insert('rotation_quaternion', frame=current_frame)


    return


# Process all the poses from the pose file
def process_poses(
        input_path,
        neural_smplx_path,
        gender,
        fps_source,
        fps_target,
        start_origin,
        person_id=1,
):

    print('Processing: ' + input_path)

    poses, lhposes, rhposes, trans = get_input_data(input_path)
    
    model_path = neural_smplx_path
    # if gender == 'female':
    #     model_path = female_model_path
    #     for k,v in BODY_JOINT_NAMES.items():
    #         BODY_JOINT_NAMES[k] = 'f_avg_' + v
    # elif gender == 'male':
    #     model_path = male_model_path
    #     for k,v in BODY_JOINT_NAMES.items():
    #         BODY_JOINT_NAMES[k] = 'm_avg_' + v
    # else:
    #     print('ERROR: Unsupported gender: ' + gender)
    #     sys.exit(1)

    # Limit target fps to source fps
    if fps_target > fps_source:
        fps_target = fps_source

    print(f'Gender: {gender}')
    print(f'Number of source poses: {str(poses.shape[0])}')
    print(f'Source frames-per-second: {str(fps_source)}')
    print(f'Target frames-per-second: {str(fps_target)}')
    print('--------------------------------------------------')

    setup_scene(model_path, fps_target)

    scene = bpy.data.scenes['Scene']
    sample_rate = int(fps_source/fps_target)
    scene.frame_end = (int)(poses.shape[0]/sample_rate)

    # Retrieve pelvis world position.
    # Unit is [cm] due to Armature scaling.
    # Need to make copy since reference will change when bone location is modified.
    bpy.ops.object.mode_set(mode='EDIT')
    pelvis_position = Vector(bpy.data.armatures[0].edit_bones[BODY_JOINT_NAMES[0]].head)
    # bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.mode_set(mode='POSE')

    source_index = 0
    frame = 1

    offset = np.array([0.0, 0.0, 0.0])

    while source_index < poses.shape[0]:
        # print('Adding pose: ' + str(source_index))
        if start_origin:
            if source_index == 0:
                offset = np.array([trans[source_index][0], trans[source_index][1], 0])

        # Go to new frame
        scene.frame_set(frame)

        process_pose(frame, 
            poses[source_index], 
            lhposes[source_index],
            rhposes[source_index],
            (trans[source_index] - offset), 
            pelvis_position)
        source_index += sample_rate
        frame += 1
    bpy.ops.object.mode_set(mode='OBJECT')
    return frame


def export_animated_mesh(output_path):
    # Create output directory if needed
    output_dir = os.path.dirname(output_path)
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # Select only skinned mesh and rig
    bpy.ops.object.select_all(action='DESELECT')
    bpy.data.objects[ROOT_NAME].select_set(True)
    bpy.data.objects[ROOT_NAME].children[0].select_set(True)

    if output_path.endswith('.glb'):
        print('Exporting to glTF binary (.glb)')
        # Currently exporting without shape/pose shapes for smaller file sizes
        bpy.ops.export_scene.gltf(filepath=output_path, export_format='GLB', export_selected=True, export_morph=False)
    elif output_path.endswith('.fbx'):
        print('Exporting to FBX binary (.fbx)')
        bpy.ops.export_scene.fbx(filepath=output_path, use_selection=True, add_leaf_bones=False)
    else:
        print('ERROR: Unsupported export format: ' + output_path)
        sys.exit(1)

    return


if __name__ == '__main__':
    try:
        if bpy.app.background:

            parser = argparse.ArgumentParser(description='Create keyframed animated skinned SMPL mesh from VIBE output')
            parser.add_argument('--input', dest='input_path', type=str, default="./demo/smplerx_result/smplx",
                                help='Input file or directory')
            parser.add_argument('--output', dest='output_path', type=str, default="./demo/fbx_result/res.fbx",
                                help='Output file or directory')
            parser.add_argument('--neural_smplx_path', type=str, default="./demo/T_pos/smplx-neutral.fbx", 
                                help='t-pos path')
            parser.add_argument('--fps_source', type=int, default=30,
                                help='Source framerate')
            parser.add_argument('--fps_target', type=int, default=30,
                                help='Target framerate')
            parser.add_argument('--gender', type=str, default='male',
                                help='Always use specified gender')
            parser.add_argument('--start_origin', type=bool, default=True,
                                help='Start animation centered above origin')
            parser.add_argument('--person_id', type=int, default=1,
                                help='Detected person ID to use for fbx animation')

            parser.add_argument('-noaudio', action='store_true',
                                help='dummy - for blender loading')
            parser.add_argument('--background', action='store_true',
                                help='dummy - for blender loading')
            args = parser.parse_args()

            input_path = args.input_path
            output_path = args.output_path

            if not os.path.exists(input_path):
                print('ERROR: Invalid input path')
                sys.exit(1)

            fps_source = args.fps_source
            fps_target = args.fps_target

            gender = args.gender

            start_origin = args.start_origin

        # end if bpy.app.background

        startTime = time.perf_counter()

        # Process data
        cwd = os.getcwd()

        # Turn relative input/output paths into absolute paths
        if not input_path.startswith(os.path.sep):
            input_path = os.path.join(cwd, input_path)

        if not output_path.startswith(os.path.sep):
            output_path = os.path.join(cwd, output_path)

        print('Input path: ' + input_path)
        print('Output path: ' + output_path)

        if not (output_path.endswith('.fbx') or output_path.endswith('.glb')):
            print('ERROR: Invalid output format (must be .fbx or .glb)')
            sys.exit(1)

        # Process pose file

        poses_processed = process_poses(
            input_path=input_path,
            neural_smplx_path=args.neural_smplx_path,
            gender=gender,
            fps_source=fps_source,
            fps_target=fps_target,
            start_origin=start_origin,
            person_id=args.person_id
        )
        export_animated_mesh(output_path)

        print('--------------------------------------------------')
        print('Animation export finished.')
        print(f'Poses processed: {str(poses_processed)}')
        print(f'Processing time : {time.perf_counter() - startTime:.2f} s')
        print('--------------------------------------------------')
        sys.exit(0)

    except SystemExit as ex:
        if ex.code is None:
            exit_status = 0
        else:
            exit_status = ex.code

        print('Exiting. Exit status: ' + str(exit_status))

        # # Only exit to OS when we are not running in Blender GUI
        # if bpy.app.background:
        #     sys.exit(exit_status)