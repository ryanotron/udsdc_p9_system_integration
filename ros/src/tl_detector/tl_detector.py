#!/usr/bin/env python
import rospy
from std_msgs.msg import Int32
from geometry_msgs.msg import PoseStamped, Pose
from styx_msgs.msg import TrafficLightArray, TrafficLight
from styx_msgs.msg import Lane
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from light_classification.tl_classifier import TLClassifier
from scipy.spatial import KDTree
import tf
import cv2
import yaml
import keras
from keras.models import load_model
import tensorflow
import numpy as np

STATE_COUNT_THRESHOLD = 1
graph = None

class TLDetector(object):
    def __init__(self):
        rospy.init_node('tl_detector')

        self.pose = None
        self.waypoints = None
        self.waypoint_tree = None
        self.camera_image = None
        self.lights = []
        self.train_flag = False
        self.img_count = 4
        self.img_skip = 1
        self.last_image_stamp = None
        self.sample_count = 0
        
        self.blind = rospy.get_param('~blind', False)
        if self.blind:
            rospy.loginfo("TL detector operating blind")
        
        self.collect_samples = rospy.get_param('~collect_samples', False)    

        # minimum distance in wp index for collecting non-tl images
        self.min_landscape_idx = rospy.get_param('~min_landscape_idx', 200)
        self.max_landscape_idx = rospy.get_param('~max_landscape_idx', 1000)

        # maximum distance in wp index for collecting tl images
        self.min_light_idx = rospy.get_param('~min_light_idx', 30)
        self.max_light_idx = rospy.get_param('~max_light_idx', 50)

        self.samples_path = rospy.get_param('~samples_path', '/home/ryan/samples/')
        self.sample_period = rospy.get_param('~sample_period', 2.0) # how many seconds between landscape samples
        # consequently, at distances between min_landscape_idx and max_light_idx, no image will be collected
        
        # whether to use neural network model for light classification
        self.use_model = rospy.get_param('~use_model', False)
        self.model_name = rospy.get_param('~model_name', None)
        self.grey_model = rospy.get_param('~grey_model', False)

        self.model = None        
        if self.model_name:
            try:
                keras.backend.clear_session()
                self.model = load_model(self.model_name)
                global graph
                graph = tensorflow.get_default_graph()
                
                self.model._make_predict_function()
                rospy.loginfo('loaded model %s', self.model_name)
            except:
                rospy.logerr('failed to load model %s', self.model_name)
                self.use_model = False

        sub1 = rospy.Subscriber('/current_pose', PoseStamped, self.pose_cb, queue_size=1)
        sub2 = rospy.Subscriber('/base_waypoints', Lane, self.waypoints_cb, queue_size=1)

        '''
        /vehicle/traffic_lights provides you with the location of the traffic light in 3D map space and
        helps you acquire an accurate ground truth data source for the traffic light
        classifier by sending the current color state of all traffic lights in the
        simulator. When testing on the vehicle, the color state will not be available. You'll need to
        rely on the position of the light and the camera image to predict it.
        '''
        sub3 = rospy.Subscriber('/vehicle/traffic_lights', TrafficLightArray, self.traffic_cb, 
                                queue_size=1)
        if not self.blind:
            sub6 = rospy.Subscriber('/image_color', Image, self.image_cb, queue_size=1)

        config_string = rospy.get_param("/traffic_light_config")
        self.config = yaml.load(config_string)

        self.upcoming_red_light_pub = rospy.Publisher('/traffic_waypoint', Int32, queue_size=1)

        self.bridge = CvBridge()
        self.light_classifier = TLClassifier()
        self.listener = tf.TransformListener()

        self.state = TrafficLight.UNKNOWN
        self.last_state = TrafficLight.UNKNOWN
        self.last_wp = -1
        self.state_count = 0
        
        rospy.loginfo('TL detector READY!')
        rospy.loginfo('TL detector READY!!')
        rospy.loginfo('TL detector READY!!!')

        rospy.spin()

    def pose_cb(self, msg):
        self.pose = msg

    def waypoints_cb(self, waypoints):
        self.waypoints = waypoints
        
        if not self.waypoint_tree:
            waypoints_2D = [[wp.pose.pose.position.x, wp.pose.pose.position.y]\
                            for wp in waypoints.waypoints]
            self.waypoint_tree = KDTree(waypoints_2D)

    def traffic_cb(self, msg):
        self.lights = msg.lights
        if self.blind:
            light_wp, state = self.process_traffic_lights()
            light_wp = light_wp if state == TrafficLight.RED else -1
            self.upcoming_red_light_pub.publish(Int32(light_wp))        

    def image_cb(self, msg):
        """Identifies red lights in the incoming camera image and publishes the index
            of the waypoint closest to the red light's stop line to /traffic_waypoint

        Args:
            msg (Image): image from car-mounted camera

        """
        if self.img_count < self.img_skip:
            self.img_count += 1
            return

        if self.last_image_stamp == None:
            self.last_image_stamp = rospy.Time.now()
        
        self.img_count = 0
        self.has_image = True
        self.camera_image = msg
        light_wp, state = self.process_traffic_lights()

        '''
        Publish upcoming red lights at camera frequency.
        Each predicted state has to occur `STATE_COUNT_THRESHOLD` number
        of times till we start using it. Otherwise the previous stable state is
        used.
        '''
        if self.state != state:
            self.state_count = 0
            self.state = state
        elif self.state_count >= STATE_COUNT_THRESHOLD:
            self.last_state = self.state
            light_wp = light_wp if state == TrafficLight.RED else -1
            self.last_wp = light_wp
            self.upcoming_red_light_pub.publish(Int32(light_wp))
        else:
            self.upcoming_red_light_pub.publish(Int32(self.last_wp))
        self.state_count += 1

    def get_closest_waypoint(self, x, y):
        """Identifies the closest path waypoint to the given position
            https://en.wikipedia.org/wiki/Closest_pair_of_points_problem
        Args:
            pose (Pose): position to match a waypoint to

        Returns:
            int: index of the closest waypoint in self.waypoints

        """
        #TODO implement
        closest_idx = self.waypoint_tree.query([x, y], 1)[1]
        return closest_idx

    def get_light_state(self, light):
        """Determines the current color of the traffic light

        Args:
            light (TrafficLight): light to classify

        Returns:
            int: ID of traffic light color (specified in styx_msgs/TrafficLight)

        """
        # TODO implement classification
        #---------------------------------------------------------
        #if(not self.has_image):
            #self.prev_light_loc = None
            #return False

        #cv_image = self.bridge.imgmsg_to_cv2(self.camera_image, "bgr8")

        #Get classification
        #return self.light_classifier.get_classification(cv_image)
        #---------------------------------------------------------
        return light.state

    def process_traffic_lights(self):
        """Finds closest visible traffic light, if one exists, and determines its
            location and color

        Returns:
            int: index of waypoint closes to the upcoming stop line for a traffic light (-1 if none exists)
            int: ID of traffic light color (specified in styx_msgs/TrafficLight)

        """
        closest_light = None
        line_wp_idx = None

        # List of positions that correspond to the line to stop in front of for a given intersection
        stop_line_positions = self.config['stop_line_positions']
        if self.pose and self.waypoint_tree:
            car_wp_idx = self.get_closest_waypoint(self.pose.pose.position.x, self.pose.pose.position.y)

            #TODO find the closest visible traffic light (if one exists)
            diff = len(self.waypoints.waypoints)
            for i, light in enumerate(self.lights):
                line = stop_line_positions[i]
                tmp_wp_idx = self.get_closest_waypoint(line[0], line[1])
                
                d = tmp_wp_idx - car_wp_idx
                if d >= 0 and d < diff:
                    diff = d
                    closest_light = light
                    line_wp_idx = tmp_wp_idx

        if closest_light:
            # data collection calibration helper
            dee = line_wp_idx - car_wp_idx
            #if not self.collect_samples:
                #rospy.loginfo('next light, %d waypoint away', dee)

            state = self.get_light_state(closest_light)
            
            if not (self.model is None) and dee < self.max_light_idx:
                img = self.bridge.imgmsg_to_cv2(self.camera_image, desired_encoding='rgb8')
                img = np.float32(img)/255.0
                #img = np.float32(img)

                if self.grey_model:
                    img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
                    img = 2.*img - 1.
                
                # shift image randomly 20 pixels, to avoid being stuck
                tx = np.random.randint(-20, 21)
                ty = np.random.randint(-20, 21)
                if self.grey_model:
                    tx = np.random.randint(-50, 51)
                    ty = np.random.randint(-50, 51)
                
                T = np.float32([[1, 0, tx], [0, 1, ty]])
                nrow, ncol = img.shape[:2]
                img = cv2.warpAffine(img, T, (ncol, nrow))

                if self.grey_model:
                    img = np.reshape(img, [nrow, ncol, 1])
                
                img = np.expand_dims(img, axis=0)
                
                global graph
                with graph.as_default():
                    predict = self.model.predict(img)
                    label = np.argmax(predict[0])
                    #rospy.loginfo(str(predict[0]))
                    rg = predict[0, 0]/predict[0, 2]
                    gr = predict[0, 2]/predict[0, 0]
                    
                    if self.use_model:
                        state = label
                    rospy.loginfo('infer %d, know %d, rg %4.2f, gr %4.2f', label, state, rg, gr)

            if self.collect_samples:
                idx_dist = line_wp_idx - car_wp_idx
                t_process = rospy.Time.now()
                dt_sample = (t_process - self.last_image_stamp).to_sec()
                #rospy.loginfo('next light, %d waypoint away, last sample %5.2f [s] behind', 
                              #idx_dist, dt_sample)
                if idx_dist > self.min_landscape_idx and idx_dist < self.max_landscape_idx \
                   and dt_sample > self.sample_period:
                    self.last_image_stamp = t_process
                    im = self.bridge.imgmsg_to_cv2(self.camera_image, desired_encoding='bgr8')
                    fname = self.samples_path + '3__' + str(idx_dist) + '_' \
                            + str(t_process.secs) + '_' + str(t_process.nsecs) + '.png'
                    self.sample_count += 1
                    rospy.loginfo('sample %s, count %d', fname, self.sample_count)
                    cv2.imwrite(fname, im)
                elif idx_dist < self.max_light_idx and idx_dist > self.min_light_idx:
                    self.last_image_stamp = t_process
                    label = '3__'
                    if state == TrafficLight.RED:
                        label = '0__'
                    elif state == TrafficLight.YELLOW:
                        label = '1__'
                    elif state == TrafficLight.GREEN:
                        label = '2__'
                    im = self.bridge.imgmsg_to_cv2(self.camera_image, desired_encoding='bgr8')
                    fname = self.samples_path + label + str(idx_dist) + '_' \
                            + str(t_process.secs) + '_' + str(t_process.nsecs) + '.png'
                    self.sample_count += 1
                    rospy.loginfo('sample %s, count %d', fname, self.sample_count)
                    cv2.imwrite(fname, im)

            return line_wp_idx, state
        
        return -1, TrafficLight.UNKNOWN

if __name__ == '__main__':
    try:
        TLDetector()
    except rospy.ROSInterruptException:
        rospy.logerr('Could not start traffic node.')
