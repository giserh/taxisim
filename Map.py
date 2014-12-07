'''
Created on Dec 5, 2014

@author: mengyalan
'''

from KDTree import KDTree
import csv
from Node import Node
from Link import Link

#Represents a roadmap, has a set of Nodes and Links
class Map:
    min_lat = float('inf')
    max_lat = float('-inf')
    min_lon = float('inf')
    max_lon = float('-inf')

    
    #Finds the Node which is nearest to a given coordinate.  Uses a KDTree for fast lookup
    #Params:
        # lat - the query latitude
        # lon - the query longitude
        # LAT_METERS - one degree latitude equals this many meters
        # LON_METERS - one degree longitude equals this many meters (assume earth is "flat enough")
    #Returns:
        # A Node object
    def get_nearest_node(self, lat, lon, LAT_METERS=111194.86461, LON_METERS=84253.1418965):
        if(lat < self.min_lat or lat > self.max_lat or lon < self.min_lon or lon > self.max_lon):
            return None
        #convert lat/lon to meters (approximate, assume NYC is flat)
        coordinates = (lat*LAT_METERS,lon*LON_METERS)
        node, dist = self.lookup_kd_tree.nearest_neighbor_query(coordinates)
        return node

    
    # Gets the region that a point is in geometrically
    # Params:
        # point - an array-like that contains coordinates (like a Node or tuple)
    # Returns: The region, which is a leaf node of the region_kd_tree
    def get_region(self, point):
        return self.region_kd_tree.nearest_neighbor_query(point)
    

            
    #Finds the maximum speed of any link in the graph
    def get_max_speed(self):
        max_speed = 0.0
        for link in self.links:
            max_speed = max(max_speed, link.speed)
        return max_speed

    #Builds the Map from CSV files describing the Nodes and LInks
    #Params:
        # nodes_fn - the name of the CSV file containing Node info
        # links_fn - the name of the CSV file containing Link info
        # lookup_id_size - the leaf_size for the Node lookup kd tree.  Should be small for fastest performance
        # region_id_size - the leaf_size for the region kd tree.  Should be large
    def __init__(self, nodes_fn, links_fn, lookup_kd_size = 2, region_kd_size = 1000):
        self.nodes = [] # A list of all Nodes
        self.nodes_by_id = {} # Maps integer node_ids to Node objects
        self.links = [] # A list of all Links
        self.links_by_node_id = {} # Maps (begin_node_id, end_node_id) to Link objects
        
        #Read nodes file and create node objects
        with open(nodes_fn, "r") as f:
            csv_reader = csv.reader(f)
            csv_reader.next() #throw out header
            for line in csv_reader:
                #Unpack CSV line
                [node_id,is_complete,num_in_links,num_out_links,osm_traffic_controller,
                     longitude,latitude,osm_changeset,birth_timestamp,death_timestamp,
                     region_id] = line
                
                #grow the bounds of the map if necessary
                [latitude, longitude] = map(float, [latitude, longitude])
                self.min_lat = min(self.min_lat, latitude)
                self.max_lat = max(self.max_lat, latitude)
                self.min_lon = min(self.min_lon, longitude)
                self.max_lon = max(self.min_lon, longitude)
                
                node = Node(int(node_id), latitude, longitude, int(region_id))
                self.nodes.append(node)
                self.nodes_by_id[node.node_id] = node
        
        #read Links file and create links
        with open(links_fn, "r") as f:
            csv_reader = csv.reader(f)
            csv_reader.next() #throw out header
            for line in csv_reader:
                #unpack line
                [link_id,begin_node_id,end_node_id,begin_angle,end_angle,street_length,
                     osm_name,osm_class,osm_way_id,startX,startY,endX,endY,osm_changeset,
                     birth_timestamp,death_timestamp] = line
                #convert strings to int ids                     
                [begin_node_id, end_node_id] = map(int, [begin_node_id, end_node_id])
                
                #If the begin_node and end_node exist, create a Link between them
                if(begin_node_id in self.nodes_by_id and end_node_id in self.nodes_by_id):
                    begin_node = self.nodes_by_id[begin_node_id]
                    end_node = self.nodes_by_id[end_node_id]
                    
                    #Create the Link object and set properties
                    link = Link(begin_node_id, float(street_length))
                    link.origin_node = begin_node
                    link.connecting_node = end_node
                    
                    #Add Link to forward and backward adjacency lists
                    begin_node.forward_links.append(link)
                    end_node.backward_links.append(link)
                    
                    #Add Link to the list and the lookup table
                    self.links.append(link)
                    self.links_by_node_id[begin_node_id, end_node_id] = link
        
        #Finally, index nodes using KD Trees
        self.region_kd_tree = KDTree(self.nodes, leaf_size = region_kd_size)
        self.lookup_kd_tree = KDTree(self.nodes, leaf_size = lookup_kd_size)


#A simple test that tries various leaf_sizes for the lookup_kd_tree
#Turns out smaller is always better
def benchmark_node_lookup():
    from datetime import datetime
    print("Loading")
    nyc_map = Map("nyc_map4/nodes.csv", "nyc_map4/links.csv")
    max_speed = nyc_map.get_max_speed()
    
    print("Max speed = " + str(max_speed))    
    
    print("Reading file")
    sample_trips = []
    with open('sample.csv', 'r') as f:
        r = csv.reader(f)
        r.next() #throw out header
        for line in r:
            [medallion, hack_license, vendor_id, rate_code, store_and_fwd_flag, pickup_datetime,
                 dropoff_datetime, passenger_count, trip_time_in_secs, trip_distance,
                 pickup_longitude, pickup_latitude, dropoff_longitude, dropoff_latitude] = line
            
            [pickup_longitude, pickup_latitude, dropoff_longitude, dropoff_latitude] = map(
                float, [pickup_longitude, pickup_latitude, dropoff_longitude, dropoff_latitude])
            sample_trips.append([pickup_longitude, pickup_latitude, dropoff_longitude, dropoff_latitude])
            if(len(sample_trips) >= 10000):
                break
    
    
    for leaf_size in [1,2,3,4,5,6,7,8,9,10,20,30,40,50]:
        d1 = datetime.now()
        nyc_map.lookup_kd_tree = KDTree(nyc_map.nodes, leaf_size=leaf_size)
        d2 = datetime.now()
        for [pickup_longitude, pickup_latitude, dropoff_longitude, dropoff_latitude] in sample_trips:
            orig = nyc_map.get_nearest_node(pickup_latitude, pickup_longitude)
            #print "calls : " + str(nyc_map.lookup_kd_tree.calls)
            dest = nyc_map.get_nearest_node(dropoff_latitude, dropoff_longitude)
            #print "calls : " + str(nyc_map.lookup_kd_tree.calls)
        d3 = datetime.now()
        
        print "leaf_size=" + str(leaf_size) + "   build time: " + str(d2 - d1) + "   query time: " + str(d3 - d2)


if(__name__=="__main__"):
    benchmark_node_lookup()