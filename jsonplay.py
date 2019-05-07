#!/usr/bin/env python
#title           :jsonplay.py
#description     :Messing around playing with JSON and dictionaries
#author          :Daren Fulwell - daren.fulwell@gmail.com
#date            :01-5-2019
#version         :0.1
#notes           :Input file contains a JSON array with some default stuff - want to create a list of dictionaries
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
handler = logging.FileHandler('jsonplay.log')
handler.setLevel(logging.INFO)
# create a logging format
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(handler)
logger.info("==== Start jsonplay.py ====")

# Initialise variables
username = "dfulwell"
password = "C1sco123!"
router_dict = {}
router_list = []
router_dict_file = "router-inventory-structure.json"
router_inventory_file = "router-list.csv"

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
		command="show ip int brief"
		connection.find_prompt()
		output=connection.send_command(command)
		lines=output.rsplit('\r\n')
		
		interface=thisrouter['interfaces'][0]
		
		for line in lines:
			print(line)
			fields=line.split()
			print(fields)
			if (len(fields)>1) and (fields[0] != "Interface"):
				interface['interface']=fields[0]
				interface['ip-address']=fields[1]
				print(interface)
				thisrouter['interfaces'].append(interface)
				
		connection.disconnect()
		#print(output)
		print(thisrouter)

# Function to fetch state from ASA and parse it
def fetch_asa_state (thisrouter):
	logger.info("Not yet attempting to connect to %s",thisrouter["device-ID"])
	print("Nothing to see here!")
	
# Import JSON file for router dictionary structure
router_dict=fetch_router_dict(router_dict_file)
if router_dict != False:
	# File found and loaded OK
	logger.info("Successfully retrieved router structure")
	
	# loop through inventory list and retrieve initial info
	router_list=initialise_router_list(router_dict,router_inventory_file)

	for router in router_list:
		if router['device-type']=="RTR":
			fetch_router_state(router)
		elif router['device-type']=="SW":
			fetch_router_state(router)
		elif router['device-type']=="ASA":
			fetch_asa_state(router)

logger.info("==== End jsonplay.py ====")
	