#!/usr/bin/env python
import rospy
import tf
from gazebo_msgs.msg import LinkStates
import sys, rospy, tf, rospkg
from gazebo_msgs.srv import *
from geometry_msgs.msg import *
from copy import deepcopy

def get_links_gazebo(link_states_msg):
    # Call back to retrieve the object you are interested in
    global input_linkname
    global pose
    poses = {'world': link_states_msg.pose[0]} # get world link
    for (link_idx, link_name) in enumerate(link_states_msg.name):
        modelname = link_name.split('::')[0]
        if input_linkname == modelname:
            poses[modelname] = link_states_msg.pose[link_idx]

    pose = poses[input_linkname]

def main():
    rospy.init_node('gazebo2tfframe')

    # Create TF broadcaster -- this will publish a frame give a pose
    tfBroadcaster = tf.TransformBroadcaster()
    # SUbscribe to Gazebo's topic where all links and objects poses within the simulation are published
    rospy.Subscriber('gazebo/link_states', LinkStates, get_links_gazebo)
    
    global pose
    i = 0
    while not rospy.is_shutdown() and i<1:
        if pose is not None:
            pos = pose.position
            ori = pose.orientation
            pose.position.z -= 0.93
            i = i + 1
            # Publish transformation given in pose
            tfBroadcaster.sendTransform((pos.x, pos.y, pos.z - 0.93), (ori.x, ori.y, ori.z, ori.w), rospy.Time.now(), input_linkname, 'world')


if __name__ == '__main__':
    main()