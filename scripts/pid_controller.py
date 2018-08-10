#!/usr/bin/python
import tf
import sys
import rospy
import signal
import traceback
import numpy as np
import command_values as cmds
from old_pid_class import PID, PIDaxis
from geometry_msgs.msg import Pose, Twist
from pidrone_pkg.msg import Mode, RC, State
from std_msgs.msg import Float32, Empty, Bool
from three_dim_vec import Position, Velocity, Error, RPY


class PIDController(object):
    ''' Controls the flight of the drone by running a PID controller on the
    error calculated by the desired and current velocity and position of the drone
    '''

    def __init__(self):
        # Initialize the current and desired modes
        self.current_mode = Mode('DISARMED')
        self.desired_mode = Mode('DISARMED')

        # Initialize in velocity control
        self.position_control = False

        # Initialize the current and desired positions
        self.current_position = Position()
        self.desired_position = Position(z=0.3)

        # Initialize the position error
        self.position_error = Error()

        # Initialize the current and desired velocities
        self.current_velocity = Velocity()
        self.desired_velocity = Velocity()

        # Initialize the velocity error
        self.velocity_error = Error()

        # Set the distance that a velocity command will move the drone (m)
        self.desired_velocity_travel_distance = 0.5
        self.desired_velocity_travel_time = 0.0
        self.desired_velocity_start_time = None

        # Initialize the primary PID
        self.pid = PID()

        # Initialize the error used for the PID which is vx, vy, z where vx and
        # vy are velocities, and z is the error in the altitude of the drone
        self.pid_error = Error()

        # Initialize the 'position error to velocity error' PIDs:
        # left/right (roll) pid
        self.lr_pid = PIDaxis(0.0500, -0.00000, 0.000, midpoint=0, control_range=(-10.0, 10.0))
        # front/back (pitch) pid
        self.fb_pid = PIDaxis(-0.0500, 0.0000, -0.000, midpoint=0, control_range=(-10.0, 10.0))
        ### # up/down (throttle) pid
        ### self.ud_pid = PIDaxis(-0.0500, 0.0000, -0.000, midpoint=0, control_range=(-10.0, 10.0))

        # Initialize the yaw velocity
        self.yaw_velocity = 0.0

        # store the correction velocity constant
        self.cvc_vel = 1.0

        # angle compensation values (to account for tilt of drone)
        self.mw_angle_comp_x = 0
        self.mw_angle_comp_y = 0
        self.mw_angle_alt_scale = 1.0
        self.mw_angle_coeff = 0.2

        # Initialize the current and  previous roll, pitch, yaw values
        self.current_rpy = RPY()
        self.previous_rpy = RPY()

        # initialize  the current angular_velocities
        self.current_angular_velocity = Velocity()
        self.previous_angular_velocity = Velocity()

        # initialize the current and previous states
        self.current_state = State()
        self.previous_state = State()

        # Store the command publisher
        self.cmdpub = None


    # ROS SUBSCRIBER CALLBACK METHODS
    #################################
    def current_state_callback(self, state):
        """ Store the drone's current state for calculations """
        self.previous_state = self.current_state
        self.current_state = state
        self.calc_angle_comp_values()
        self.state_to_three_dim_vec_structs()

    def desired_pose_callback(self, msg):
        """ Update the desired pose """
        self.desired_position.x = msg.position.x
        self.desired_position.y = msg.position.y
        self.desired_position.z = msg.position.z

#TODO THE TIMES 4 IS FROM THE OLD CODE. TEST THIS AND TRY TO REMOVE THIS BY INCREASING P TERM
    def desired_twist_callback(self, msg):
        """ Update the desired twist """
        self.desired_velocity.x = msg.linear.x * 4.0
        self.desired_velocity.y = msg.linear.y * 4.0
        self.desirded_velocity.z = msg.linear.z * 4.0
        self.calculate_travel_time()

    def current_mode_callback(self, msg):
        """ Update the current mode """
        self.current_mode = msg.mode

    def desired_mode_callback(self, msg):
        """ Update the desired mode """
        self.desired_mode = msg.mode

    def toggle_callback(self, msg):
        """ Set whether or not position control is enabled """
        self.position_control = msg.data
        print "Position Control", self.position_control

    def reset_callback(self, empty):
        self.desired_position = Position(z=self.current_position.z)
        self.desired_velocity = Velocity()

    # subscribe to /pidrone/picamera/transforming_on_first_image
    def tofi_callback(self, msg):
        """ Set the correction velocity constant based on if the pose estimate
        is from transforming on the first image """
        self.cvc_vel = 1.0 if msg.data else 3.0


    # Step Method
    #############
    def step(self):
        """ Returns the commands generated by the pid """
        self.calc_error()
        if self.desired_velocity.magnitude() > 0:
            self.adjust_desired_velocity()
        return self.pid.step(self.pid_error, self.yaw_velocity)

    # HELPER METHODS
    ################
    def state_to_three_dim_vec_structs(self):
        """
        Convert the values from the state estimator into ThreeDimVec structs to
        make calculations concise
        """
        # store the positions
        pose = self.current_state.pose_with_covariance.pose
        self.current_position.x = pose.position.x
        self.current_position.y = pose.position.y
        self.current_position.z = pose.position.z

        # store the linear velocities
        twist = self.current_state.twist_with_covariance.twist
        self.current_velocity.x = twist.linear.x
        self.current_velocity.y = twist.linear.y
        self.current_velocity.z = twist.linear.z

        # store the angular velocities
        self.previous_angular_velocity = self.current_angular_velocity
        self.current_angular_velocity.x = twist.angular.x
        self.current_angular_velocity.y = twist.angular.y
        self.current_angular_velocity.z = twist.angular.z

        # store the orientations
        self.previous_rpy = self.current_rpy
        quaternion = (pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w)
        r,p,y = tf.transformations.euler_from_quaternion(quaternion)
        self.current_rpy = RPY(r,p,y)

    def calc_angle_comp_values(self):
        """ Calculates angle compensation values to account for the tilt of the
        drone when calculating the velocity error """
        dt = self.current_state.header.stamp.to_sec() - self.previous_state.header.stamp.to_sec()
        vx = self.current_angular_velocity.x
        vy = self.current_angular_velocity.y
        self.mw_angle_comp_x = vx * self.mw_angle_coeff
        self.mw_angle_comp_y = vy * self.mw_angle_coeff

        self.mw_angle_alt_scale = np.cos(self.current_rpy.r) * np.cos(self.current_rpy.p)
        self.pid.throttle.mw_angle_alt_scale = self.mw_angle_alt_scale

# TODO THIS IS A PROTOTYPE METHOD THAT NEEDS TESTING
    def adjust_desired_velocity(self):
        """ Set the desired velocity back to 0 once the drone has traveled the
        amount of time that causes it to move the specified desired velocity
        travel distance
        """
        curr_time = rospy.get_time()
        if self.desired_velocity_start_time is not None:
            duration = curr_time - self.desired_velocity_start_time
            if duration > self.desired_velocity_travel_time:
                self.desired_velocity = Velocity(0, 0, 0)
                self.desired_velocity_start_time = None
        else:
            self.desired_velocity_start_time = curr_time

# TODO THIS IS A PROTOTYPE METHOD THAT NEEDS TESTING
    def world_to_body_frame_rotation(self):
        current_position_matrix = np.matrix([self.current_position.x,
                                            self.current_position.y,
                                            self.current_position.z])

        r,p,y = tf.transformations.euler_from_quaternion(self.current_orientation_quaternion)
        cr,sr,cp,sp,cy,sy = np.cos(r),np.sin(r),np.cos(p),np.sin(p),np.cos(y),np.sin(y)
# TODO THIS COULD BE THE TRASNPOSE
        rotation_matrix = np.matrix(
        [   [cy*cp,      -sy*cr + cy*sp*sr,      sy*sr + cy*sp*cr],
            [sy*cp,      cy*cr + sy*sp*sr,       -cy*sr + sy*sp*cr],
            [-sp,        cp*sr,                  cp*cr]
        ])
        # rotation_matrix = rotation_matrix.transpose()

        rotated_current_position = current_position_matrix.dot(rotation_matrix)
        self.current_position = Position(rotated_current_position[0,0], rotated_current_position[0,1], rotated_current_position[0,2])

#     def calc_z_velocity(self):
#         ''' Caculate the velocity in the z direction from the z position values
#         since these are directly measured
#         '''
# # TODO try using z velocity from camera!
#         self.current_calculated_z_velocity = (self.z - self.previous_z)/(self.pose_delta_time)
    def calc_error(self):
        """ Calculate the error in velocity, and if in position hold, add the
        error from lr_pid and fb_pid to the velocity error to control the
        position of the drone
        """
        # calculate the velocity error
        self.velocity_error = self.desired_velocity - self.current_velocity
        # calculate the z position error
        dz = self.desired_position.z - self.current_position.z
        # calculate the pid_error from the above values
        altitude = self.current_position.z
        err = Error()
        err.x = (self.velocity_error.x - self.mw_angle_comp_x) * altitude
        err.y = (self.velocity_error.y - self.mw_angle_comp_y) * altitude
        err.z = dz
        # multiply by 100 to account for the fact that code was originally written using cm
        self.pid_error = err * 100
        if self.position_control:
            self.position_error = self.desired_position - self.current_position
            # calculate a value to add to the velocity error based based on the
            # position error in the x (roll) direction
            # the time step doesn't matter because this is a p only controller
            lr_step = self.lr_pid.step(self.position_error.x, 1)
            correction_vel_x = lr_step * self.cvc_vel
            # calculate a value to add to the velocity error based based on the
            # position error in the y (pitch) direction
            # the time step doesn't matter because this is a p only controller
            fb_step = self.fb_pid.step(self.position_error.y, 1)
            correction_vel_y = fb_step * self.cvc_vel
# TODO CHECK SIGNS
            self.pid_error.x += correction_vel_x
            self.pid_error.y += correction_vel_y

# TODO THIS IS A PROTOTYPE METHOD THAT NEEDS TESTING
    def reduce_magnitude(self, error):
        """ Returns a vector with the same direction but with a reduced
        magnitude to enable small steps when a large error exists. This is meant
        to act as a very simple motion planning algorithm """
        error_array = np.array([error.x, error.y, error.z])
        magnitude = np.sqrt(error_array.dot(error_array))
        if magnitude > 0.05:
            error_array = (error_array / magnitude) * 0.05
        return Error(error_array[0], error_array[1], error_array[2])

# TODO THIS IS A PROTOTYPE METHOD THAT NEEDS TESTING
    def calculate_travel_time(self):
        ''' return the amount of time that desired velocity should be used to
        calculate the error in order to move the drone the specified travel
        distance for a desired velocity
        '''
        return self.velocity_command_travel_distance/ self.desired_velocity.magnitude()

    def reset(self):
        ''' Set desired_position to be current position, set
        filtered_desired_velocity to be zero, and reset both the PositionPID
        and VelocityPID
        '''
# TODO test this
        # reset position control variables
        self.position_error = Error(0,0,0)
        self.desired_position = Position(self.current_position.x,self.current_position.y,0.3)
        # reset velocity control_variables
        self.velocity_error = Error(0,0,0)
        self.desired_velocity = Velocity(0,0,0)
        # reset the pid
        self.pid.reset()

    def ctrl_c_handler(self, signal, frame):
        """ Gracefully handles ctrl-c """
        print 'Caught ctrl-c\n Stopping Controller'
        sys.exit()

    def publish_cmd(self, cmd):
        """Publish the controls to /pidrone/controller"""
        msg = RC()
        msg.roll = cmd[0]
        msg.pitch = cmd[1]
        msg.yaw = cmd[2]
        msg.throttle = cmd[3]
        self.cmdpub.publish(msg)


if __name__ == '__main__':

    # Verbosity between 0 and 2, 2 is most verbose
    verbose = 2

    # ROS Setup
    ###########
    rospy.init_node('pid_controller')

    # create the PIDController object
    pid_controller = PIDController()

    # Publishers
    ############
    pid_controller.cmdpub = rospy.Publisher('/pidrone/fly_commands', RC, queue_size=1)

    # Subscribers
    #############
    rospy.Subscriber('/pidrone/state', State, pid_controller.current_state_callback)
    rospy.Subscriber('/pidrone/desired/pose', Pose, pid_controller.desired_pose_callback)
    rospy.Subscriber('/pidrone/desired/twist', Twist, pid_controller.desired_twist_callback)
    rospy.Subscriber('/pidrone/mode', Mode, pid_controller.current_mode_callback)
    rospy.Subscriber('/pidrone/desired/mode', Mode, pid_controller.desired_mode_callback)
    rospy.Subscriber("/pidrone/toggle_transform", Bool, pid_controller.toggle_callback)
    rospy.Subscriber("/pidrone/reset_transform", Empty, pid_controller.reset_callback)
    rospy.Subscriber('/pidrone/picamera/transforming_on_first_image', Bool, pid_controller.tofi_callback)

    # Non-ROS Setup
    ###############
    # set up ctrl-c handler
    signal.signal(signal.SIGINT, pid_controller.ctrl_c_handler)
    # set the loop rate (Hz)
    loop_rate = rospy.Rate(10)
    print 'PID Controller Started'
    while not rospy.is_shutdown():
        # Steps the PID. If we are not flying, this can be used to
        # examine the behavior of the PID based on published values
        fly_command = pid_controller.step()

        # reset the pids after arming
        if pid_controller.current_mode == 'DISARMED':
            if pid_controller.desired_mode == 'ARMED':
                pid_controller.reset()
        # if the drone is flying, send the fly_command
        elif pid_controller.current_mode == 'FLYING':
            if pid_controller.desired_mode == 'FLYING':
                # Publish the ouput of pid step method
                pid_controller.publish_cmd(fly_command)

        if verbose >= 2:
            if pid_controller.position_control:
                print 'current position:', pid_controller.current_position
                print 'desired position:', pid_controller.desired_position
                print 'position error:', pid_controller.position_error
            else:
                print 'current velocity:', pid_controller.current_velocity
                print 'desired velocity:', pid_controller.desired_velocity
                print 'velocity error:  ', pid_controller.velocity_error
            print 'pid_error:       ', pid_controller.pid_error
        if verbose >= 1:
            print 'r,p,y,t:', fly_command

        loop_rate.sleep()