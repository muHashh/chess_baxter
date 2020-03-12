#!/bin/sh

cd ../../
catkin_make 
xfce4-terminal -H -e "bash devel/setup.bash && roslaunch baxter_gazebo baxter_world.launch"
xfce4-terminal -H -e "bash devel/setup.bash && rosrun baxter_tools enable_robot.py -e; rosrun baxter_interface joint_trajectory_action_server.py"
xfce4-terminal -H -e "bash devel/setup.bash && roslaunch baxter_moveit_config baxter_grippers.launch" 
xfce4-terminal -H -e "bash devel/setup.bash && rosrun lab4_pkg pick_and_plave_moveit.py" 