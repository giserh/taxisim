# -*- coding: utf-8 -*-
"""
Represents a tree of worker and manager processes for efficient parallel computing
on distributed systems.  Is most useful when a large number of workers are required
and when the amount of data that needs to be sent to them is large. In this case,
a hierarchy of managers can all send data to their children workers at the same time.
Managers also do work of their own once they have dispatched their children, for
maximum CPU usage.

Created on Wed Jan 14 13:08:19 2015

@author: Brian Donovan briandonovan100@gmail.com
"""

import cPickle as pickle


from mpi4py import MPI
from Queue import Queue
from datetime import datetime




# Utility function, which sends an object to another MPI process in chunks
# This results in more robust communication, since large messages seem to produce
# unpredictable behavior.
# Params:
    # obj - A picklable object to be sent
    # dest - The MPI process ID, which we are sending to
    # chunk_size - The pickled object will be cut into strings of this size before sending    
    # ACK_INTERVAL - After every N chunks, verify that the other process has received
        # before continuing
def chunk_send(obj, dest, chunk_size=1000000, ACK_INTERVAL=10):
    #First pickle the object
    pickled_obj = pickle.dumps(obj)

        
    start_id = 0
    requests = []
    # Iterate through chunks of the string
    while(start_id < len(pickled_obj)):
        
        # Carefully avoid array overflow
        end_id = min(start_id + chunk_size, len(pickled_obj))
        
        # Send the chunk, and remember the request ID
        request = MPI.COMM_WORLD.isend(pickled_obj[start_id:end_id], dest=dest) 
        requests.append(request)
        start_id = end_id
        
        # Every ACK_INTERVAL chunks, ensure that the receiver actually got them
        if(len(requests) >= ACK_INTERVAL):
            # print("%d ) waiting for ack %s " % (MPI.COMM_WORLD.Get_rank(), str(requests)) )
            MPI.Request.Waitall(requests)
            # print("%d ) got it. " % (MPI.COMM_WORLD.Get_rank()) )
            requests = []
    
    # Inform the receiver that we are done
    request = MPI.COMM_WORLD.isend("[[MSG_OVER]]", dest=dest)
    requests.append(request)
    
    # Ensure that the receiver got the last few chunks and the [[MSG_OVER]]
    MPI.Request.Waitall(requests)
        
   
    
# The counterpart to chunk_send().  Receives a pickled object in several parts,
# then reassembles it.
# Params:
        # source - The MPI process ID, which will send us strings
def chunk_recv(source):
    chunks = []
    # Keep receiving messages until [[MSGOVER]] is received
    while(True):
        msg = MPI.COMM_WORLD.recv(source=source)
        # print ("----- %d received msg of size %d" % (MPI.COMM_WORLD.Get_rank(), len(msg)))
        
        # If the special [[MSG_OVER]] string is received, we are done
        if(msg=="[[MSG_OVER]]"):
            break
        
        # Otherwise, add the string to the list of received strings
        chunks.append(msg)
    
    # Concatenate the strings, then unpickle
    pickled_obj = "".join(chunks)
    del(chunks)
    return pickle.loads(pickled_obj)
    




# Represents a hierarchy of worker and manager processes.  This facilitates fast dissemination of
# data to workers for efficient parallel computations
class ProcessTree:
    
    # Simple constructor.  Should be called by ALL MPI Processes
    # Params:
        # desired_size - The number of desired nodes in the process tree
        # branching_factor - Max number of children each manager should have
        # batch_size - the number of jobs to be performed on each node
    def __init__(self, desired_size, branching_factor=2, batch_size=1, debug_mode=False):
        self.desired_size = desired_size
        self.branching_factor = branching_factor
        self.batch_size = batch_size
        self.debug_mode = debug_mode
        
        
        self.dbg("__init__")        
        
        self._id = MPI.COMM_WORLD.Get_rank()
        self.parent_id = None
        self.child_ids = []
        self.child_sizes = []
    
    
       
    # Prepares the ProcessTree for use.  Should be called by ALL MPI Processes
    # The parent process will organize the remaining processes into a hierarchy by telling them
    # who their parent and children are.
    # This method will return for the master process, but workers will wait for instructions.
    def prepare(self):
        rank = MPI.COMM_WORLD.Get_rank()
        if(rank==0):
            
            self.dbg("Growing tree")
            # If we are the main process, build the tree to plan the computation
            self.root = PTNode(self.desired_size, self.branching_factor)
            self.root.grow()
            
            self.dbg("Sending tree to other processes")
            # Tell all of the other processes who their parent and children are
            self._send_parents_and_children(self.root)
            
            self.parent_id = None
            self.child_ids = self.root.get_child_ids()
            self.child_sizes = self.root.get_child_sizes()

            self.dbg("Done")
        else:
            # Wait for the main process to tell us who our family is
            # Note that the main process tells itself
            self.dbg("Receiving tree")
            
            self.parent_id, self.child_ids, self.child_sizes = chunk_recv(source=0)
            self.dbg("Waiting for instructions from parent %d"% (self.parent_id))
            self._wait_for_instructions()
    
    
    # Evaluates a function on many different inputs in parallel. It should
    # only be called by the master process. Does not return until ALL child
    # processes are complete
    # Params:
        # func - the function to be run
        # const_args - Any arguments that are the same in all evaluations of the function.
            # Can be a tuple or list if multiple arguments are required
        # args_list - A list of arguments that may change between each evaluation.
            # Can be a list of lists or tuples if the function requires multiple inputs
    def map(self, func, const_args, args_list):
        if(MPI.COMM_WORLD.Get_rank()==0):
            # The max number of jobs we can do in parallel is self.desired_size
            # So we will cut args_list into slices of this size or smaller and process
            # them individually
            start_pos = 0
            while(start_pos < len(args_list)):
                end_pos = start_pos + self.desired_size * self.batch_size # Create slice of correct size
                end_pos = min(end_pos, len(args_list)) # Avoid array overflow
                
                # Process the job
                self.dbg("Running (%d - %d) / %d" % (start_pos, end_pos, len(args_list)))
                self._map(func, const_args, args_list[start_pos:end_pos])
                
                # Advance to the next slice
                start_pos = end_pos
        else:
            raise Exception("close() should only be called by master process.")
    
    # Closes the ProcessTree, allowing all of the MPI Processes to escape.  Should only
    # be called by the master process.
    def close(self):
        if(MPI.COMM_WORLD.Get_rank()==0):
            self._close()
        else:
            raise Exception("close() should only be called by master process.")
    
    
    # Internal method which tells all of the children of this process to close.
    def _close(self):
        self.dbg("Closing")
        # Send the close message to each child
        for i in self.child_ids:
            chunk_send("[[CLOSE]]", dest=i)
            
    # Internal function which splits arg_list into pieces, and sends the corresponding
    # jobs to the children nodes.
    # Params:
        # func - the function to be run
        # const_args - Any arguments that are the same in all evaluations of the function.
            # Can be a tuple or list if multiple arguments are required
        # args_list - A list of arguments that may change between each evaluation.
            # Can be a list of lists or tuples if the function requires multiple inputs
    def _map(self, func, const_args, args_list):
        
        # Grab the first batch of jobs for ourselves.  We will do that work after
        # our children have been dispatched
        first_batch = args_list[0:self.batch_size]
        
        
        
        self.dbg("Sending jobs to children: " + str(self.child_ids))
        # We must send the appropriate number of jobs to each child.  Since the tree
        # may not be perfectly symmetric, each child may not receive the same number of jobs.
        # The number of jobs should be size of that child's subtree (number of nodes including itself)
        start_pos = self.batch_size # Start here instead of 0, since we saved a slice for ourselves
        for i in xrange(len(self.child_ids)):
            # Create a slice that is the right size for that child
            end_pos = start_pos + self.child_sizes[i] * self.batch_size
            # Avoid array out of bounds, may send a job that is smaller than the capacity
            end_pos = min(end_pos, len(args_list))
            
            child_args = args_list[start_pos:end_pos] # Slice the args list
            
            self.dbg("Sending jobs %d - %d to child %d" % (start_pos, end_pos, self.child_ids[i]))
            # Send the data
            # MPI.COMM_WORLD.isend((func, const_args, child_args), dest=self.child_ids[i])
            chunk_send((func, const_args, child_args), dest=self.child_ids[i])
                        
            
            
            
            
            start_pos = end_pos # Advance to the next slice
            
            # Out of jobs - the remaining children are unnecessary
            if(start_pos >= len(args_list)):
                self.dbg("Out of jobs")
                break
        num_useful_children = i+1
        
        
        self.dbg("Evaluating function")
        # While children are working, do our own job
        for args in first_batch:
            func(const_args, args)

        # Free memory - we don't need the data anymore
        del(const_args)
        del(args_list)

        self.dbg("Waiting for children to return.")        
        # Now wait for all children to inform us that they are done
        # Only wait on children who were given a job (useful children)
        for i in xrange(num_useful_children):
            done_msg = chunk_recv(source=self.child_ids[i])
            done_msg += ""
        
        self.dbg("Finishing - inform parent %s" % str(self.parent_id))
        # Finally, inform parent that we are done
        if(self.parent_id!=None):
            chunk_send("[[DONE]]", dest=self.parent_id)
    
    
    
    # Internal recursive method which should only be called by the MASTER MPI Process
    # It tells each process who its parent and children are
    # Params:
        # ptnode - a node of the virtual process tree
    def _send_parents_and_children(self, ptnode):
        # Each PTNode's _id field corresponds to a MPI process id
        # Tell that process who its parents and children are, and how many
        # leaves are below each of its children
        if(ptnode.parent==None):
            parent_id = None
        else:
            parent_id = ptnode.parent._id
            child_ids = ptnode.get_child_ids()
            child_sizes = ptnode.get_child_sizes()
            chunk_send((parent_id, child_ids, child_sizes), dest=ptnode._id)
        
        #Make the recursive call so the rest of the tree is also informed
        for child in ptnode.children:
            self._send_parents_and_children(child)
        

            
    
    # Internal method which should only be called by MPI Processes OTHER THAN THE MASTER
    # It loops forever, waiting for the master to give it jobs or tell it to close
    def _wait_for_instructions(self):
        
        while(True):
            #Receive data from the parent
            data = chunk_recv(source=self.parent_id)
            self.dbg("Received data")
            
            if(data=="[[CLOSE]]"):
                # First, kill all of the children
                self._close()
                # Then, exit the loop
                break
            else:
                # Unpack the data
                func, const_args, args_list = data
                
                if(self.child_ids==[]):
                    self.dbg("I am a leaf")
                    # If this is a leaf node, just run the function on the given inputs
                    # If batch_size > 1, then run the function several times
                    for args in args_list:
                        func(const_args, args)
                        
                    # Inform the parent that we are done
                    chunk_send("[[DONE]]", dest=self.parent_id)
                else:
                    self.dbg("I am an internal node.")
                    # If this is an internal node, split the args_list and send
                    # Everything to the children
                    self._map(func, const_args, args_list)
                    
    # A method for printing debug messages
    # Includes the MPI process ID and timestamp in the message
    def dbg(self, msg):
        if(self.debug_mode):
            rank = MPI.COMM_WORLD.Get_rank()
            t = datetime.now()
            print( "(%d) [%s] %s\n" % (rank, str(t), msg))
    

# Represents a Node in a tree, which is used to organize MPI processes into a hierarchy.
# Note that there are no MPI calls in this class.  The master process should just build
# a tree of PTNodes in order to plan the execution strategy.
class PTNode:
    _id = -1
    parent = None
    
    def __init__(self, desired_size, branching_factor):
        self.desired_size = desired_size
        self.size = 1
        self.branching_factor = branching_factor
        self.children = []
    
    # Grows a tree of a given size and branching factor.  These are given by
    # self.desired_size and self.branching_vactor
    def grow(self):
        # First, use BFS to create a tree of the desired size
        q = Queue()
        q.put(self)
        num_nodes = 1
        
        #Keep adding children to the existing nodes until the tree is too big
        while(q.not_empty and num_nodes < self.desired_size):
            node = q.get()            
            
            # Each node should have a certain number of children given by the branching factor
            for i in xrange(self.branching_factor):
                # We might hit the limit while in the middle of adding children to this node
                if(num_nodes >= self.desired_size):
                    break
                
                # Create the child and doubly link it to the parent
                child = PTNode(self.desired_size, self.branching_factor)
                child.parent = node
                node.children.append(child)
                
                # Put into the queue so it can later get children of its own if necessary
                q.put(child)
                num_nodes += 1
                
        # Finally, recursively hand out ID numbers and sizes        
        self._compute_ids_and_sizes(0)
    
    
    # Internal method which recursively hands out ID numbers and sizes to a tree
    # that has already been built.  Ids are handed out using BFS ordering, and the
    # size indicates the number of nodes in this node's subtree (including this node)
    def _compute_ids_and_sizes(self, start_id):
        # This node starts with the given ID and size of 1
        self._id = start_id
        self.size = 1
        
        # Increment start id so there are no collisions
        start_id += 1
        
        # Recursively call children
        for child in self.children:
            child._compute_ids_and_sizes(start_id)
            
            # We know that (child.size) IDs were handed out in the recursive call
            # So increment by this much to avoid collisions
            start_id += child.size
            
            # Include the child's size in this size
            self.size += child.size
    
    # Returns the id numbers of each of this PTNode's children
    def get_child_ids(self):
        return [child._id for child in self.children]
    
    # Returns the sizes of each child's subtree.  They should add up to one less than
    # this node.size
    def get_child_sizes(self):
        return [child.size for child in self.children]
    
    # Returns the maximum height of the tree
    def get_height(self):
        if(self.children==[]):
            return 0
        child_heights = [child.get_height() for child in self.children]
        return max(child_heights) + 1
    
    # Returns the total number of leaves in the tree
    def get_num_leaves(self):
        if(self.children==[]):
            return 1
        child_leaves = [child.get_num_leaves() for child in self.children]
        return sum(child_leaves)
    
    
    # Debug method, which recursively p
    def print_tree(self):
        ptnode = self
        if(ptnode.parent==None):
            parent_id = None
        else:
            parent_id = ptnode.parent._id
        child_ids = ptnode.get_child_ids()
        print ( str(self._id) + ") Parent: " + str(parent_id) + "  Children: " + str(child_ids) + "  Size: " + str(self.size))
        
        for child in self.children:
            child.print_tree()
    
    


# A simple function for testing purposes
def times(a,b):
    rank = MPI.COMM_WORLD.Get_rank()
    t = datetime.now()
    msg = str(a) + " x " + str(b).rjust(3,"0") + " = " + str(a*b)
    print( "(%d) [%s] %s\n" % (rank, str(t), msg))
    #print str(a) + " x " + str(b).rjust(3,"0") + " = " + str(a*b) + "  [" + str(rank) + "]"

#  A simple test
if(__name__=="__main__"):

    
    # Build and prepare the process tree 
    t = ProcessTree(16, 3, batch_size=4, debug_mode=True)
    t.prepare()
    
    
    if(MPI.COMM_WORLD.Get_rank()==0):
        a = 3 # Constant arguments
        b_list = range(101) # List of arguments
        t.map(times, a, b_list)
        t.close()
    
