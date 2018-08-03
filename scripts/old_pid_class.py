#!/usr/bin/env python
from __future__ import division
from three_dim_vec import Error
import rospy


#####################################################
#						PID							#
#####################################################
class PIDaxis():
    def __init__(self, kp, ki, kd, kp_upper=None, i_range=None, d_range=None, control_range=(1000, 2000), midpoint=1500):
        # Tuning
        self.kp = kp
        self.ki = ki
        self.kd = kd
        # Config
        self.kp_upper = kp_upper
        self.i_range = i_range
        self.d_range = d_range
        self.control_range = control_range
        self.midpoint = midpoint
        self.smoothing = True
        # Internal
        self._old_err = None
        self._p = 0
        self._i = 0
        self._d = 0
        self._dd = 0
        self._ddd = 0

    def step(self, err, time_elapsed):
        if self._old_err is None:
            # First time around prevent d term spike
            self._old_err = err

        # Find the p component
        if self.kp_upper is not None and err < 0:
            self._p = err * self.kp_upper
        else:
            self._p = err * self.kp

        # Find the i component
        self._i += err * self.ki * time_elapsed
        if self.i_range is not None:
            self._i = max(self.i_range[0], min(self._i, self.i_range[1]))

        # Find the d component
        self._d = (err - self._old_err) * self.kd / time_elapsed
        if self.d_range is not None:
            self._d = max(self.d_range[0], min(self._d, self.d_range[1]))
        self._old_err = err

        # Smooth over the last three d terms
        if self.smoothing:
            self._d = (self._d * 8.0 + self._dd * 5.0 + self._ddd * 2.0)/15.0
            self._ddd = self._dd
            self._dd = self._d

        # Calculate control output
        raw_output = self._p + self._i + self._d
        output = min(max(raw_output + self.midpoint, self.control_range[0]), self.control_range[1])

        return output


class PID:

    height_factor = 1.238
    battery_factor = 0.75
# TODO NOTE, THERE IS NO KP UPPER AS IN ORIGINAL CODE?
    def __init__(self,

                 roll=PIDaxis(6., 4.0, 0.5, control_range=(1400, 1600), midpoint=1500),
                 roll_low=PIDaxis(4., 0.2, 0.0, control_range=(1400, 1600), midpoint=1500),

                 pitch=PIDaxis(6., 4.0, 0.5, control_range=(1400, 1600), midpoint=1500),
                 pitch_low=PIDaxis(4., 0.2, 0.0, control_range=(1400, 1600), midpoint=1500),

                 yaw=PIDaxis(0.0, 0.0, 0.0),

                 # Kv 2300 motors have midpoint 1300, Kv 2550 motors have midpoint 1250
                 throttle=PIDaxis(1.0/height_factor * battery_factor, 0.5/height_factor * battery_factor,
                                  2.0/height_factor * battery_factor, kp_upper=1.0/height_factor * battery_factor,
                                  i_range=(-400, 400), control_range=(1200, 2000), d_range=(-40, 40), midpoint=1250),
                 throttle_low=PIDaxis(1.0/height_factor * battery_factor, 0.05/height_factor * battery_factor,
                                      2.0/height_factor * battery_factor, kp_upper=1.0/height_factor * battery_factor,
                                      i_range=(0, 400), control_range=(1200, 2000), d_range=(-40, 40), midpoint=1250)
                 ):

        self.trim_controller_cap_plane = 0.05 #5
        self.trim_controller_thresh_plane = 0.0001

        self.roll = roll
        self.roll_low = roll_low

        self.pitch = pitch
        self.pitch_low = pitch_low

        self.yaw = yaw

        self.trim_controller_cap_throttle = 5.0
        self.trim_controller_thresh_throttle = 5.0

        self.throttle = throttle
        self.throttle_low = throttle_low

        self.sp = None
        self._t = None

        # Steve005 presets
        self.roll_low._i = 50
        self.pitch_low._i = -6 #46.35

        self.throttle_low.init_i = 50
        self.throttle.init_i = 0.0
        self.throttle.mw_angle_alt_scale = 1.0
        self.reset()

    def reset(self, state_controller=None):
        self._t = None
        self.throttle_low._i = self.throttle_low.init_i
        self.throttle._i = self.throttle.init_i

        if state_controller is not None:
            state_controller.set_z = state_controller.initial_set_z

    def step(self, error, cmd_yaw_velocity=0):
        print 'roll_low_i', self.roll_low._i
        print 'pitch_low_i', self.pitch_low._i
        # First time around prevent time spike
        if self._t is None:
            time_elapsed = 1
        else:
            time_elapsed = rospy.get_time() - self._t

        self._t = rospy.get_time()

        # Compute roll command
        if abs(error.x) < self.trim_controller_thresh_plane:
            cmd_r = self.roll_low.step(error.x, time_elapsed)
            self.roll._i = 0
        else:
            if error.x > self.trim_controller_cap_plane:
                self.roll_low.step(self.trim_controller_cap_plane, time_elapsed)
            elif error.x < -self.trim_controller_cap_plane:
                self.roll_low.step(-self.trim_controller_cap_plane, time_elapsed)
            else:
                self.roll_low.step(error.x, time_elapsed)

            cmd_r = self.roll_low._i + self.roll.step(error.x, time_elapsed)

        # Compute pitch command
        if abs(error.y) < self.trim_controller_thresh_plane:
            cmd_p = self.pitch_low.step(error.y, time_elapsed)
            self.pitch._i = 0
        else:
            if error.y > self.trim_controller_cap_plane:
                self.pitch_low.step(self.trim_controller_cap_plane, time_elapsed)
            elif error.y < -self.trim_controller_cap_plane:
                self.pitch_low.step(-self.trim_controller_cap_plane, time_elapsed)
            else:
                self.pitch_low.step(error.y, time_elapsed)

            cmd_p = self.pitch_low._i + self.pitch.step(error.y, time_elapsed)

        # Compute yaw command
        cmd_y = 1500 + cmd_yaw_velocity

        # Compute throttle command
        if abs(error.z) < self.trim_controller_thresh_throttle:
            cmd_t = self.throttle_low.step(error.z, time_elapsed)
            self.throttle_low._i += self.throttle._i
            self.throttle._i = 0
        else:
            if error.z > self.trim_controller_cap_throttle:
                self.throttle_low.step(self.trim_controller_cap_throttle, time_elapsed)
            elif error.z < -self.trim_controller_cap_throttle:
                self.throttle_low.step(-self.trim_controller_cap_throttle, time_elapsed)
            else:
                self.throttle_low.step(error.z, time_elapsed)

            cmd_t = self.throttle_low._i + self.throttle.step(error.z, time_elapsed)

            # jgo: this seems to mostly make a difference before the I term has
            # built enough to be stable, but it really seems better with it. To
            # see the real difference, compare cmd_t / mw_angle_alt_scale to
            # cmd_t * mw_angle_alt_scale and see how it sinks. That happens to
            # a less noticeable degree with no modification.
            cmd_t = cmd_t / max(0.5, self.throttle.mw_angle_alt_scale)

        # Print statements for the low and high i components
        # print "Roll  low, hi:", self.roll_low._i, self.roll._i
        # print "Pitch low, hi:", self.pitch_low._i, self.pitch._i
        # print "Throttle low, hi:", self.throttle_low._i, self.throttle._i
        return [cmd_r, cmd_p, cmd_y, cmd_t]
