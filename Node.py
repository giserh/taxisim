import csv
from Link import Link
from Grid import set_up_grid
import numpy as np

# TODO: REMOVE THE DUPLICATE STUFF TAKING INTO ACCOUNT NONES


# A vertex in our map
# (edge class not used -> simply used lists within the node)
class Node:

    def __init__(self, node_id, latitude, longitude, region):
        self.node_id = node_id
        self.lat = float(latitude)
        self.long = float(longitude)
        self.region = int(region)

        # Used during the route calculator
        #   -> this keeps track of the node previous to this one in a path
        # i.e. If the path was A->C->B->D, B.came_from == C
        self.came_from = None

        # Used for DFS
        self.discovered = False

        # Keeps track of how far away we are from the start_node
        self.best_time = float("INF")

        # These are nodes that are connected by edges that start at the current
        # node and their weights
        self.forward_links = []
        self.backward_links = []

        self.is_forward_arc_flags = {}
        self.is_backward_arc_flags = {}

        ######################################################
        #  Used in multiple dijkstra arcflag precomputation  #
        ######################################################

        # Tells if the node is a boundary node
        self.is_boundary_node = False

        # Uniquely indexes the boundary nodes in each region
        # This index refers to a slot in time_from_boundary_node
        self.boundary_node_id = -1

        # During the dijkstra algorithm, give a set of which indices were
        # updated
        # self.was_updated = set()

        # For multi-origin dijkstra, storing the time from each boundary node
        self.time_from_boundary_node = np.array([])

        # A snapshot of the time_from_boundary_node from the last expansion
        self.time_snapshot = np.array([])

        # For each boundary node path, shows where this particular node came
        # from
        self.forward_predecessors = np.array([])
        self.backward_predecessors = np.array([])

        # Checks if the node is currently in the queue (won't add otherwise)
        # self.in_queue = False

        # The number of times this node has been updated since its last
        # expansion
        self.update_count = 0

        # Identifies which region this node belongs to
        self.region_id = (None, None)

    # Compare time_from_boundary_node with the snapshot from its last expansion
    def get_domination_value(self):
        return np.sum(self.time_from_boundary_node != self.time_snapshot)

    # Given an node_id, gives its weight
    def add_connecting_node(self, node_id, weight, speed, time):
        self.forward_links.append(Link(node_id, weight, speed, time))

    def set_arc_flags(self, node_id, hex_string):
        new_list = hex_deconverter(hex_string)
        self.is_forward_arc_flags[node_id] = new_list
        self.is_backward_arc_flags[node_id] = new_list

    def get_min_boundary_time(self):
        return np.min(self.time_from_boundary_node)

    def get_boundary_time_inf_count(self):
        return np.sum(self.time_from_boundary_node == float('inf'))

    def get_boundary_time_sum(self):
        finite_numbers = self.time_from_boundary_node[
            np.isfinite(self.time_from_boundary_node)]
        return np.sum(finite_numbers)

    def get_priority_key(self, use_domination_value):
        if(use_domination_value):
            return -self.get_domination_value()
        else:
            return self.get_min_boundary_time()


# For converting the regions in the ArcFlags csv file back into binary from hex
def hex_deconverter(hex_string):
    newString = bin(int(hex_string, 16))[2:]
    newList = map(int, list(newString))
    if len(newList) < 400:
        newList = [0] * (400 - len(newList)) + newList
    return newList

##############################
#        NON ARC FLAG        #
##############################


# Instead of using ID's as the keys, they use actual nodes.
# Also sets up boundary nodes and arcflags.
def fix_nodes(dict_of_nodes, has_speeds, has_arc_flags):
    for node_id in dict_of_nodes:
        curr_node = dict_of_nodes[node_id]

        # TODO: remove new_forward_links and forward_arc_flags
        new_forward_links = []
        forward_arc_flags = []

        for connecting_link in curr_node.forward_links:
            try:
                new_node = dict_of_nodes[connecting_link.origin_node_id]
                if new_node != -1:
                    connecting_link.origin_node = curr_node
                    connecting_link.connecting_node = new_node
                    new_forward_links.append(connecting_link)

                    # Set is_forward_arc_flags[new_node] = secondDict{}
                    # secondDict[RegionNumber] = True or False
                    if has_arc_flags is None:
                        curr_node.is_forward_arc_flags[new_node] = False
                    else:
                        forward_arc_flags[new_node] = (
                            curr_node.is_forward_arc_flags[connecting_link])
            except(KeyError):
                pass
        curr_node.forward_links = new_forward_links
        if has_arc_flags is not None:
            curr_node.is_forward_arc_flags = forward_arc_flags

    for node_id in dict_of_nodes:
        node = dict_of_nodes[node_id]
        for connecting_link in node.forward_links:
            #connecting_link.origin_node = node
            connecting_node = connecting_link.connecting_node
            if connecting_node is None:
                pass
            connecting_node.backward_links.append(connecting_link)
            if connecting_node.region != node.region:
                connecting_node.is_boundary_node = True


# Returns a set of nodes with all their forward_links properly set
def set_up_nodes(time_file, arc_flag_file):
    dict_of_links = dict()
    all_links = csv.reader(open("nyc_map4/links.csv", 'rb'), delimiter=',')
    speed_of_links = None
    if time_file is not None:
        speed_of_links = csv.reader(open(time_file, 'rb'), delimiter=',')
    arc_flags = None
    if arc_flag_file is not None:
        arc_flags = csv.reader(open(arc_flag_file, 'rb'), delimiter=',')
    # Dictionary should be start_node_id->setOfAllLinks that have that
    # start_node
    header = True
    for link in all_links:
        if header:
            header = False
            continue
        if link[1] in dict_of_links:
            dict_of_links[link[1]].append(link)
        else:
            dict_of_links[link[1]] = []
            dict_of_links[link[1]].append(link)
    # Key is start_node, list of all streets that start at that node
    header = True
    # Key is start_node, adds speeds of links
    if speed_of_links is not None:
        for link in speed_of_links:
            if header:
                header = False
                continue
            curr_list = dict_of_links[link[0]]
            for orig_link in curr_list:
                # If the end_nodes are the same (streets are the same)
                if orig_link[2] == link[1]:
                    orig_link.append(link[3])  # Speed of link
                    orig_link.append(link[4])  # Time of link
    header = True
    # Key is start_node, adds arc_links
    if arc_flags is not None:
        for link in arc_flags:
            if header:
                header = False
                continue
            curr_list = dict_of_links[link[0]]
            for orig_link in curr_list:
                # If the end_nodes are the same (streets are the same)
                if orig_link[2] == link[1]:
                    orig_link.append(link[2])
    dict_of_nodes = dict()
    all_nodes = csv.reader(open("nyc_map4/nodes.csv", 'rb'), delimiter=',')
    counter = 0
    for node in all_nodes:
        # Want to ignore the header line
        if counter != 0:
            # Creates the nodes and put them in the dictionary
            # with the node_id as the key
            # node_id, ycoord, xcoord, grid_region_id
            new_node = Node(node[0], node[6], node[5], node[10])
            try:
                list_of_links = dict_of_links[new_node.node_id]
                for link in list_of_links:
                    # if the links.csv file has 16 columns
                    if len(link) == 16 and link[2] != new_node.node_id:
                        new_node.add_connecting_node(
                            # end_node_id, street_length, speed = 1,
                            # street_length/1
                            link[2], link[5], 1, float(link[5]) / 1)

                    # if the links.csv file has 19 columns
                    if (len(link) == 19 and link[2] != new_node.node_id and
                            float(link[17]) > 0):
                        new_node.add_connecting_node(
                            link[2], link[5], link[16], link[17])
                        new_node.set_arc_flags(link[2], link[18])

                    # if the links.csv file has 18 columns
                    if (len(link) == 18 and link[2] != new_node.node_id and
                            float(link[17]) > 0):
                        new_node.add_connecting_node(
                            link[2], link[5], link[16], link[17])
            except(KeyError):
                pass
            dict_of_nodes[new_node.node_id] = new_node
        counter += 1
    # Changes what they connections keys are (from node_id's to nodes)
    fix_nodes(dict_of_nodes, speed_of_links, arc_flags)
    set_of_nodes = set()
    for node_id in dict_of_nodes:
        set_of_nodes.add(dict_of_nodes[node_id])
    return set_of_nodes


# Returns an array that goes like this
# [MaxLat, MinLat, MaxLong, MinLong]
def get_node_info(arr):
    node_info = [-1000, 1000, -1000, 1000]
    for node in arr:
        if float(node.lat) > node_info[0]:
            node_info[0] = float(node.lat)
        if float(node.lat) < node_info[1]:
            node_info[1] = float(node.lat)
        if float(node.long) > node_info[2]:
            node_info[2] = float(node.long)
        if float(node.long) < node_info[3]:
            node_info[3] = float(node.long)
    return node_info


# If no ArcFlags, arc_flag_file is None
def get_correct_nodes(num_divisions, time_file, arc_flag_file):
    nodes = set_up_nodes(time_file, arc_flag_file)
    if time_file is None:
        for node in nodes:
            for link in node.forward_links:
                link.speed = 5
                link.time = link.weight / 5
    node_info = get_node_info(nodes)
    return set_up_grid(
        node_info[0] + .01, node_info[1], node_info[2] + .01, node_info[3],
        num_divisions, nodes)


# Returns an array that goes like this
# [MaxLat, MinLat, MaxLong, MinLong]
def get_node_range(grid_of_nodes):
    node_info = [-1000, 1000, -1000, 1000]
    for column in grid_of_nodes:
        for region in column:
            for node in region.nodes:
                if float(node.lat) > node_info[0]:
                    node_info[0] = float(node.lat)
                if float(node.lat) < node_info[1]:
                    node_info[1] = float(node.lat)
                if float(node.long) > node_info[2]:
                    node_info[2] = float(node.long)
                if float(node.long) < node_info[3]:
                    node_info[3] = float(node.long)
    node_info[0] += .01
    node_info[2] += .01
    return node_info
