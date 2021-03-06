#!/usr/bin/env python
import sys
import copy
import rospy
import rospkg
import tf

from std_msgs.msg import (
    Empty,
)

from geometry_msgs.msg import (
    Pose,
    Point,
    Quaternion,
)

from gazebo_msgs.srv import (
    SpawnModel,
    DeleteModel,
)

import baxter_interface
import moveit_commander
import gazebo2tfframe as gazebotf

from collections import OrderedDict

class PickAndPlaceMoveIt(object):
    def __init__(self, limb, hover_distance=0.15, verbose=True):
        self._limb_name = limb  # string
        self._hover_distance = hover_distance  # in meters
        self._verbose = verbose  # bool
        self._limb = baxter_interface.Limb(limb)
        self._gripper = baxter_interface.Gripper(limb)
        print("Getting robot state... ")
        self._rs = baxter_interface.RobotEnable(baxter_interface.CHECK_VERSION)
        self._init_state = self._rs.state().enabled
        print("Enabling robot... ")

        self._robot = moveit_commander.RobotCommander()
        # This is an interface to one group of joints.  In our case, we want to use the "right_arm".
        # We will use this to plan and execute motions
        self._group = moveit_commander.MoveGroupCommander(limb+"_arm")

    def move_to_start(self, start_angles=None):
        print("Moving the {0} arm to start pose...".format(self._limb_name))

        self.gripper_open()
        self._group.set_pose_target(start_angles)
        plan = self._group.plan()
        self._group.execute(plan)
        rospy.sleep(1.0)
        print("Running. Ctrl-c to quit")

    def _guarded_move_to_joint_position(self, joint_angles):
        if joint_angles:
            self._limb.move_to_joint_positions(joint_angles)
        else:
            rospy.logerr("No Joint Angles provided for move_to_joint_positions. Staying put.")

    def gripper_open(self):
        self._gripper.open()
        rospy.sleep(1.0)

    def gripper_close(self):
        self._gripper.close()
        rospy.sleep(2.0)

    def _approach(self, pose):
        approach = copy.deepcopy(pose)
        # approach with a pose the hover-distance above the requested pose
        approach.position.z = approach.position.z + self._hover_distance

        self._group.set_pose_target(approach)
        plan = self._group.plan()
        self._group.execute(plan)

    def _retract(self):
        # retrieve current pose from endpoint
        current_pose = self._limb.endpoint_pose()
        ik_pose = Pose()
        ik_pose.position.x = current_pose['position'].x
        ik_pose.position.y = current_pose['position'].y
        ik_pose.position.z = current_pose['position'].z + self._hover_distance
        ik_pose.orientation.x = current_pose['orientation'].x
        ik_pose.orientation.y = current_pose['orientation'].y
        ik_pose.orientation.z = current_pose['orientation'].z
        ik_pose.orientation.w = current_pose['orientation'].w

        # servo up from current pose
        self._group.set_pose_target(ik_pose)
        plan = self._group.plan()
        self._group.execute(plan)

    def _servo_to_pose(self, pose):
        # servo down to release
        self._group.set_pose_target(pose)
        plan = self._group.plan()
        self._group.execute(plan)

    def pick(self, pose):
        # open the gripper
        self.gripper_open()
        # servo above pose
        self._approach(pose)
        # servo to pose
        self._servo_to_pose(pose)
        # close gripper
        self.gripper_close()
        # retract to clear object
        self._retract()

    def place(self, pose):
        # servo above pose
        self._approach(pose)
        # servo to pose
        self._servo_to_pose(pose)
        # open the gripper
        self.gripper_open()
        # retract to clear object
        self._retract()


def load_gazebo_models(table_pose=Pose(position=Point(x=1.0, y=0.0, z=0.0)),
                       table_reference_frame="world",
                       block_pose=Pose(position=Point(x=0.68, y=0.11, z=0.7825)),
                       block_reference_frame="world"):
    # Get Models' Path
    model_path = rospkg.RosPack().get_path('baxter_sim_examples')+"/models/"
    # Load Table SDF
    table_xml = ''
    with open(model_path + "cafe_table/model.sdf", "r") as table_file:
        table_xml = table_file.read().replace('\n', '')
    # Load block SDF
    block_xml = ''
    with open(model_path + "block/model.urdf", "r") as block_file:
        block_xml = block_file.read().replace('\n', '')
    # Spawn Table SDF
    rospy.wait_for_service('/gazebo/spawn_sdf_model')
    try:
        spawn_sdf = rospy.ServiceProxy('/gazebo/spawn_sdf_model', SpawnModel)
        spawn_sdf("cafe_table", table_xml, "/", table_pose, table_reference_frame)
    except rospy.ServiceException, e:
        rospy.logerr("Spawn SDF service call failed: {0}".format(e))
    # Spawn block SDF
    rospy.wait_for_service('/gazebo/spawn_sdf_model')
    try:
        spawn_sdf = rospy.ServiceProxy('/gazebo/spawn_sdf_model', SpawnModel)
        spawn_sdf("block", block_xml, "/", block_pose, block_reference_frame)
    except rospy.ServiceException, e:
        rospy.logerr("Spawn SDF service call failed: {0}".format(e))


def delete_gazebo_models():
    # This will be called on ROS Exit, deleting Gazebo models
    # Do not wait for the Gazebo Delete Model service, since
    # Gazebo should already be running. If the service is not
    # available since Gazebo has been killed, it is fine to error out
    try:
        delete_model = rospy.ServiceProxy('/gazebo/delete_model', DeleteModel)
        delete_model("cafe_table")
        delete_model("block")
    except rospy.ServiceException, e:
        rospy.loginfo("Delete Model service call failed: {0}".format(e))


def get_pick_pos(b_wanted, orientation, pick_poses=[]):
    for piece in b_wanted:
        print(piece)
        gazebotf.input_linkname = piece
        # Global variable where the object's pose is stored
        gazebotf.pose = None
        gazebotf.main()
        current_pose = gazebotf.pose.position
        pick_poses.append(Pose(
            position=current_pose,
            orientation=orientation))

    return pick_poses


def get_place_pos(b_wanted, p_wanted, orientation, place_poses=[]):
    orient = Quaternion(*tf.transformations.quaternion_from_euler(0, 0, 0))
    board_pose = Pose(Point(0.3,0.55,0.78), orient)
    frame_dist = 0.025
    origin_piece = 0.03125

    block_desired_sq = []
        
    for i in range(len(b_wanted)):
        block_desired_sq.append((b_wanted[i], p_wanted[i]))

    for pair in block_desired_sq:
        pose = copy.deepcopy(board_pose)
        row = pair[1].split('-')[0]
        pose.position.x = board_pose.position.x + frame_dist + origin_piece + int(row) * (2 * origin_piece)
        col = pair[1].split('-')[1]
        pose.position.y = board_pose.position.y - 0.55 + frame_dist + origin_piece + int(col) * (2 * origin_piece)
        pose.position.z += 0.05 # 0.018
        pose.position.z -= 0.93

        pose.orientation = orientation
        place_poses.append(pose)

    return place_poses


def main():
    moveit_commander.roscpp_initialize(sys.argv)
    #--------------------------------?
    # rospy.init_node("ik_pick_and_place_moveit")

    # # Load Gazebo Models via Spawning Services
    # # Note that the models reference is the /world frame
    # # and the IK operates with respect to the /base frame
    # # Remove models from the scene on shutdown
    # rospy.on_shutdown(delete_gazebo_models)

    # # Wait for the All Clear from emulator startup
    # rospy.wait_for_message("/robot/sim/started", Empty)
    #--------------------------------
    # NOTE: Gazebo and Rviz has different origins, even though they are connected. For this
    # we need to compensate for this offset which is 0.93 from the ground in gazebo to
    # the actual 0, 0, 0 in Rviz.
    #--------------------------------

    # An orientation for gripper fingers to be overhead and parallel to the obj
    overhead_orientation = Quaternion(x=-0.0249590815779, y=0.999649402929, z=0.00737916180073, w=0.00486450832011)

    limb = 'left' 
    hover_distance = 0.17  # meters

    starting_pose = Pose(
    position=Point(x=0.7, y=0.135, z=0.35),
    orientation=overhead_orientation)

    blocks_wanted = rospy.get_param('piece_names')
    pos_wanted = ['0-3', '0-0', '0-7', '7-3', '7-0', '7-7']
    block_pick_poses = get_pick_pos(blocks_wanted, overhead_orientation)
    block_place_poses = get_place_pos(blocks_wanted, pos_wanted, overhead_orientation)

    # blocks_wanted = ['R0','r7','R7']
    # pos_wanted = ['4-0','7-5','3-7']
    # block_pick_poses = get_pick_pos(blocks_wanted, overhead_orientation)
    # block_place_poses = get_place_pos(blocks_wanted, pos_wanted, overhead_orientation)

    pnp = PickAndPlaceMoveIt(limb, hover_distance)
    pnp.move_to_start(starting_pose)
    idx = 0
    while not rospy.is_shutdown() and idx<len(block_pick_poses):
        print("\nPicking...")
        pnp.pick(block_pick_poses[idx])
        print("\nPlacing...")
        pnp.place(block_place_poses[idx])
        idx = idx + 1
        pnp.move_to_start(starting_pose)
        
    return 0


if __name__ == '__main__':
    sys.exit(main())