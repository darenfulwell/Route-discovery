#!/usr/bin/env python
#title           :route-discovery.py
#description     :Extract of routing information from routers in the network
#author          :Daren Fulwell - daren.fulwell@gmail.com
#date            :03-5-2019
#version         :0.1
#notes           :Requires Netmiko and TextFSM to be installed
#python_version  :3.7.1
#==============================================================================

# Import the modules needed to run the script.
import json
import logging
import copy
import pprint
import time
import netmiko
from netmiko.ssh_exception import NetMikoTimeoutException
from paramiko.ssh_exception import SSHException,NoValidConnectionsError

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# create a file handler
handler = logging.FileHandler('route-discovery.log')
handler.setLevel(logging.INFO)
# create a logging format
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s') # ('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(handler)
logger.info("==== Start route-discovery.py ====")

# Initialise variables
username = "dfulwell"
password = "C1sco123!"
router_dict = {}
router_list = []
router_dict_file = "router-inventory-structure.json"
router_inventory_file = "router-list.csv"
router_list_file_prefix = "route-discovery-"
input_filename=""
load_file=False

# Function to determine subnet from interface IP and prefix
def subnet_from_ip_and_mask (ip_address, prefix):
	prefix_len=int(str(prefix).strip('/'))
	host_bits=32-prefix_len
	if host_bits!=0:
		try:
			ip_addr_bin=""
			for octet in ip_address.split('.'):
				ip_addr_bin+=format(int(octet),'08b')
		except:
			logging.info("%s not an IP address",ip_address)
		finally:
			subnet_bin=(ip_addr_bin[:(0-host_bits)])+(host_bits*'0')
			subnet_dec=""
			while subnet_bin:
				subnet_dec+=(str(int(subnet_bin[:8],2))+'.')
				subnet_bin=subnet_bin[8:]
			return (subnet_dec[:-1]+'/'+str(prefix_len))
	else:
		return (ip_address)

# Function to match next-hop to interface subnet
def match_host_and_interface (host_ip, intf_ip, prefix):
	return(subnet_from_ip_and_mask(host_ip,prefix) == subnet_from_ip_and_mask(intf_ip,prefix))

# Function to retrieve router dictionary structure
def fetch_router_dict (this_router_dict_file):

	this_router_dict=False
	try:
		logger.info("Opening router structure file %s",router_dict_file)
		with open(this_router_dict_file) as jsonfile:
			this_router_dict = json.load(jsonfile)
		jsonfile.close()
	except FileNotFoundError as fnf_error: 
		logger.error("Failed to open router structure file", exc_info=False)
	return(this_router_dict)
	
# Function to initialise router list from inventory file
def initialise_router_list (this_router_dict,this_inventory_file):
	new_router=copy.deepcopy(this_router_dict)
	this_router_list=[]
	try:
		listfile = open(this_inventory_file,"r")	
		
		for device_line in listfile:
			fields=device_line.strip().rstrip('\r\n').split(',')
			if fields[0][:1]!='#':
				new_router["device-ID"]=fields[0]
				new_router["device-IP"]=fields[1]
				new_router["device-type"]=fields[2]
				new_router["last-updated"]="INIT" #time.ctime()
				this_router_list.append(copy.deepcopy(new_router))
		
		listfile.close()
	except FileNotFoundError as fnf_error: 
		logger.error("Failed to open router inventory file %s",this_inventory_file, exc_info=False)
	else:
		logger.info("Successfully retrieved initial inventory info from %s",this_inventory_file)
	finally:
		return(this_router_list)
	
# Function to open connection to router in dictionary
def connect_to (thisrouter,thisusername,thispassword):
	device = {
		"host": thisrouter["device-IP"],
		"username": thisusername,
		"password": thispassword,
		"device_type": "cisco_ios",
		"auth_timeout": 60
	}
	protocol="SSH"
	thisconnection=False
	print("Connecting to",thisrouter['device-ID'])
	try:
		print("Trying SSH ...")
		print()
		thisconnection=netmiko.Netmiko(**device)
	except: #(SSHException,NetMikoTimeoutException,NoValidConnectionsError) :
		logger.warning("Failed to connect over %s to %s",protocol,thisrouter['device-ID'])
		device['device_type']="cisco_ios_telnet"
		protocol="Telnet"
		try:
			print("Trying Telnet ...")
			print()
			thisconnection=netmiko.Netmiko(**device)
		except: #(NetMikoTimeoutException,NoValidConnectionsError) :
			logger.warning("Failed to connect over %s to %s",protocol,thisrouter['device-ID'])
	finally:
		if thisconnection != False :
			print("Success")
			print()
			logger.info("Successfully connected to %s over %s",thisrouter['device-ID'],protocol)
		return(thisconnection)

# Function to fetch state from router and parse it
def fetch_router_state (thisrouter):
	logger.info("Attempting to connect to %s",thisrouter["device-ID"])
	connection=connect_to (thisrouter,username,password)
	if connection != False:
		# Fetch list of IP interfaces and add to router record
		command="show ip int"
		connection.find_prompt()
		output=connection.send_command(command,use_textfsm=True)
		interface=thisrouter['interfaces'][0]
		thisrouter['interfaces']=[]
		for intf in output:
			if len(intf['ipaddr']) > 0:
				interface['interface']=intf['intf']
				interface['ip-addresses']=intf['ipaddr']
				interface['prefixes']=intf['mask']
				interface['vrf']=intf['vrf']
				interface['statics']="TBC"
				interface['OSPF']="TBC"
				interface['EIGRP']="TBC"
				thisrouter['interfaces'].append(copy.deepcopy(interface))

		# Fetch extra interface info and add to router record
		command="show int"
		connection.find_prompt()
		output=connection.send_command(command,use_textfsm=True)

		for intf in output:
			for i in thisrouter['interfaces']:
				if i['interface']==intf['interface']:
					i['description']=intf['description']
					i['speed']=intf['speed']
					i['mtu']=intf['mtu']

		# Fetch static routes
		command="show ip route"
		connection.find_prompt()
		output=connection.send_command(command,use_textfsm=True)
		
		newstatic=thisrouter['statics'][0]
		thisrouter['statics']=[]
		for route in output:
			if route['protocol']=="S":
				newstatic['subnet']=route['network']
				newstatic['prefix']=route['mask']
				newstatic['next-hop']=route['nexthop_ip']
				newstatic['AD']=route['distance']
				thisrouter['statics'].append(copy.deepcopy(newstatic))

		# Check for static routing over interfaces
		for intf in thisrouter['interfaces']:
			for x in range(len(intf['ip-addresses'])):
				for route in thisrouter['statics']:
					if match_host_and_interface(route['next-hop'],intf['ip-addresses'][x],intf['prefixes'][x]):
						intf['statics']=True
						break
					else:
						intf['statics']=False
				
		connection.disconnect()
		thisrouter["last-updated"]=time.ctime()

# Function to fetch state from ASA and parse it
def fetch_asa_state (thisrouter):
	logger.info("Not yet attempting to connect to %s",thisrouter["device-ID"])
	print("Nothing to see here!")

# Function to write router list to JSON file
def write_router_state_file (thisfilename,thisrouterlist):
	success = False
	logger.info("Attempt write to %s",thisfilename)
	try:
		# Get a file object with write permission.
		file_object = open(thisfilename, 'w')
		# Save dict data into the JSON file.
		json.dump(thisrouterlist, file_object)
		success=True
		logger.info("%s created.",thisfilename)    
		file_object.close()
		
		try:
			file_object = open("last-file.cfg","w")
			file_object.write(thisfilename)
			file_object.close()
		except:
			logger.info("Last file file not written.")
			
	except: #FileNotFoundError:
		logger.info("%s not created.",thisfilename)
	finally:
		return(success)
		
# Function to read router list from JSON file		
def read_router_state_file (thisfilename):
	success = False
	logger.info("Attempt read from %s",thisfilename)
	try:
		# Open file object, read in and convert to dict
		file_object = open(thisfilename,"r")
		success = json.load(file_object)
		logger.info("%s read.",thisfilename)
		file_object.close()
	except:
		logger.info("%s not found.",thisfilename)
	finally:
		return(success)
	

	
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #


if (load_file):
	try:
		logger.info("Finding last route-discovery file")
		file_object = open("last-file.cfg","r")
		input_filename = file_object.readline()
		logger.info("Found %s",input_filename)
		file_object.close()
	except:
		logger.info("No previously written route-discovery file in directory")

if len(input_filename)>0:
	router_list=read_router_state_file (input_filename)
else:
	# Import JSON file for router dictionary structure
	router_dict=fetch_router_dict(router_dict_file)
	if router_dict != False:
		# File found and loaded OK
		logger.info("Successfully retrieved router structure")
	
		# loop through inventory list and retrieve initial info
		router_list=initialise_router_list(router_dict,router_inventory_file)

		# Retrieve router state and update router records
		for router in router_list:
			if router['device-type']=="RTR":
				fetch_router_state(router)
			elif router['device-type']=="SW":
				fetch_router_state(router)
			elif router['device-type']=="ASA":
				fetch_asa_state(router)
			
		if router_list != []:
			output_filename=router_list_file_prefix+time.strftime("%y-%m-%d-%H%M",time.gmtime())+".json"
			write_router_state_file(output_filename,router_list)

pprint.pprint(router_list)

logger.info("==== End route-discovery.py ====")
	