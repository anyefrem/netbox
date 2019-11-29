#!/usr/bin/env python

import sys
import os
import re
import yaml
import requests
import argparse
from pprint import pprint
# Local functions.py
from functions import *


if os.path.exists('./config.yml'):
	with open('./config.yml') as f:
		YAML_PARAMS = yaml.load(f)
		f.close()
else:
	print('config.yml not found!')
	sys.exit(1)

NETBOX_API = YAML_PARAMS['netbox']['api']
NETBOX_TOKEN = YAML_PARAMS['netbox']['token']
NETBOX_DEVICES = YAML_PARAMS['netbox']['url']['devices']
NETBOX_INTERFACES = YAML_PARAMS['netbox']['url']['interfaces']
NETBOX_SITES = YAML_PARAMS['netbox']['url']['sites']
NETBOX_VLANS = YAML_PARAMS['netbox']['url']['vlans']


def get_cmdline():
	parser = argparse.ArgumentParser()
	parser.add_argument('-i1', dest='upd_dev', type=str,
							help='update interface descriptions on a single device',
							required=False)
	parser.add_argument('-i2', dest='upd_site_dev', type=str,
							help='update interface descriptions across a whole site',
							required=False)
	parser.add_argument('-i3', dest='upd_dev_db', type=str,
							help='update interface descriptions of a single device in netbox',
							required=False)
	parser.add_argument('-v1', dest='upd_dev_vlans', type=str,
							help='update vlans on a single device',
							required=False)
	parser.add_argument('-v3', dest='upd_site_vlans', type=str,
							help='update vlans across a whole site',
							required=False)
	arguments = parser.parse_args()
	return arguments


def update_device_cfg(devices=None):
	try:
		if not devices:
			raise Exception('No device specified!')

		for device in devices:
			NETBOX_DEVICE_ID = netbox_get_device_id(netbox_device=device)

			data = netbox_get_interfaces()

			config_dict = dict()
			intf_list = list()
			intf_tags = ['gw', 'isp_l2', 'isp_l3', 'upd_desc', 'upd_trunk']

			for interface in data['results']:
				check_intf_tags = interface.get('tags', None)
				# MTU, MSS
				check_intf_mtu = interface.get('mtu', None)
				if check_intf_mtu:
					mtu = check_intf_mtu
					mss = int(mtu)-40
				else:
					mtu = False
					mss = False
				# Resulting dictionary defaults
				vlan_list = list()
				native_vlan = False
				access_vlan = False
				isp_l2_flag = False
				isp_l3_flag = False
				cid_isp = False
				cid_svc = False
				cid_rate = False
				switch_flag = False
				populate_flag = False
				if interface['device']['id'] == NETBOX_DEVICE_ID:
					# Pickup connected interface or LAG
					if interface['is_connected'] or 'LAG' in interface['form_factor']['label']:
						# print(interface['id'])
						pvl = populate_vlan_list(interface)
						native_vlan = pvl[0]
						vlan_list = pvl[1]
						populate_flag = True
					# Pickup interfaces tagged with predefined tags (intf_tags).
					# - 'upd_desc' is when an interface's description is manually set in Netbox,
					# and replicated from Netbox to a device.
					# - 'upd_trunk' is when an trunk's allowed vlans are manually set in Netbox,
					# and replicated from Netbox to a device.
					# - 'cid_XXX' to configure policy-map
					elif len(check_intf_tags) > 0:
						for intf_tag in check_intf_tags:
							if 'cid' in intf_tag:
								form_tag = re.sub('^cid_', '', intf_tag)
								circuits = netbox_get_circuits()
								for circuit in circuits['results']:
									if circuit['cid'] == form_tag:
										cid_isp = circuit['provider']['name']
										cid_svc = circuit['type']['name']
										# kbps -> bps
										cid_rate = int(circuit['commit_rate'])*1000
						for item in intf_tags:
							if item in check_intf_tags:
								if item == 'isp_l2':
									isp_l2_flag = True
									if netbox_check_if_switch(device):
										switch_flag = True
										if interface.get('mode', None):
											if interface['mode']['value'] == 100:
												access_vlan = interface['untagged_vlan']['vid']
								elif item == 'isp_l3':
									isp_l3_flag = True
								elif item == 'upd_trunk':
									pvl = populate_vlan_list(interface)
									native_vlan = pvl[0]
									vlan_list = pvl[1]
								populate_flag = True
					# Populate resulting list of interfaces
					if populate_flag:
						intf_list.append({
						'name': interface['name'],
						'desc': interface['description'],
						'vlans': vlan_list,
						'native_vlan': native_vlan,
						'access_vlan': access_vlan,
						'isp_l2_flag': isp_l2_flag,
						'isp_l3_flag': isp_l3_flag,
						'mtu': mtu,
						'mss': mss,
						'cid_isp': cid_isp,
						'cid_svc': cid_svc,
						'cid_rate': cid_rate,
						'switch_flag': switch_flag
						})

			config_dict['interfaces'] = intf_list

			# Load config on device
			# pprint(config_dict)
			# sys.exit(1)
			load_cfg(dst_device=device, src_config_dict=config_dict, j2_tpl='./out/tpl_intf.j2')

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def update_device_vlans(devices=None):
	try:
		if not devices:
			raise Exception('No device specified!')

		ok_count, sw_count = 0, 0

		for device in devices:
			if not netbox_check_if_switch(device):
				print('Skipping {0}'.format(device))
				continue
			else:
				sw_count += 1
				vlans_add = list()
				vlans_del = list()
				config_dict = dict()

			NETBOX_DEVICE_SITE_ID = netbox_get_device_site_id(netbox_device=device)
			vlans = netbox_get_vlans(netbox_site_id=NETBOX_DEVICE_SITE_ID)

			for vlan in vlans:
				if vlan['action'] == 'vlan_add':
					# 'id' - ID in netbox, 'vid' - VLAN ID
					vlans_add.append({
						'id': vlan['vlan_id'],
						'vid': vlan['vlan_vid'],
						'name': vlan['vlan_name']
						})
				elif vlan['action'] == 'vlan_del':
					vlans_del.append({
						'id': vlan['vlan_id'],
						'vid': vlan['vlan_vid'],
						'name': vlan['vlan_name']
						})
			
			if vlans_add:
				config_dict['vlans_add'] = vlans_add
			else:
				config_dict['vlans_add'] = None

			if vlans_del:
				config_dict['vlans_del'] = vlans_del
			else:
				config_dict['vlans_del'] = None

			# Load config on device
			# pprint(config_dict)
			# sys.exit(1)
			if vlans_add or vlans_del:
				if load_cfg(dst_device=device, src_config_dict=config_dict, j2_tpl='./out/tpl_vlan.j2'):
					ok_count += 1
			else:
				print('No vlans need to be modified!')

		if ok_count == sw_count:
			for vlan in vlans_add:
				netbox_modify_vlan(netbox_vlan_id=vlan['id'], netbox_vlan_action='vlan_add')
			for vlan in vlans_del:
				netbox_modify_vlan(netbox_vlan_id=vlan['id'], netbox_vlan_action='vlan_del')

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def update_netbox_db(device=None):
	try:
		if not device:
			raise Exception('No device specified!')
		
		NETBOX_DEVICE_ID = netbox_get_device_id(netbox_device=device)

		data = netbox_get_interfaces()

		for interface in data['results']:
			cur_desc = interface['description']
			data_to_mod = dict()
			if interface['device']['id'] == NETBOX_DEVICE_ID:
				# Pickup connected interface
				if interface['is_connected'] and interface['interface_connection']:
					static_desc_dict = YAML_PARAMS['netbox']['static_intf_desc']
					static_desc = static_desc_dict.get(interface['id'], None)
					connected_to_dev = interface['interface_connection']['interface']['device']['name']
					connected_to_intf = interface['interface_connection']['interface']['name']
					new_desc = 'Core: {0} {1}'.format(connected_to_dev.lower(), connected_to_intf)
					if static_desc and (cur_desc != static_desc):
						choise = yes_or_no('Change interface {0} (id:{1}) description: \'{2}\' <---> \'{3}\''.format(
							interface['name'], interface['id'], cur_desc, static_desc))
						if choise:
							data_to_mod['description'] = static_desc
							netbox_modify_interface(netbox_intf_id=interface['id'], data=data_to_mod)
					elif (not static_desc) and (cur_desc != new_desc):
						choise = yes_or_no('Change interface {0} (id: {1}) description: \'{2}\' <---> \'{3}\''.format(
							interface['name'], interface['id'], cur_desc, new_desc))
						if choise:
							data_to_mod['description'] = new_desc
							netbox_modify_interface(netbox_intf_id=interface['id'], data=data_to_mod)
					else:
						print('Nothing to change for interface {0} (id: {1}, exit: 1)'.format(
							interface['name'], interface['id']))
						continue
				# Pickup interface with 802.1Q Mode: Access
				elif interface.get('mode', None):
					if (interface['mode']['value'] == 100) and (interface.get('tags', None)):
						# ..and tagged 'gw'
						if 'gw' in interface['tags']:
							if interface.get('untagged_vlan', None):
								new_desc = 'Gateway: VLAN {0}'.format(interface['untagged_vlan']['vid'])
							else:
								print('Nothing to change for interface {0} (id: {1}, exit: 2)'.format(
									interface['name'], interface['id']))
								continue
							if cur_desc != new_desc:
								choise = yes_or_no('Change interface {0} (id:{1}) description: \'{2}\' <---> \'{3}\''.format(
									interface['name'], interface['id'], cur_desc, new_desc))
								if choise:
									data_to_mod['description'] = new_desc
									netbox_modify_interface(netbox_intf_id=interface['id'], data=data_to_mod)
								else:
									continue
							else:
								print('Nothing to change for interface {0} (id: {1}, exit: 3)'.format(
									interface['name'], interface['id']))
								continue
						else:
							print('Nothing to change for interface {0} (id: {1}, exit: 4)'.format(
								interface['name'], interface['id']))
							continue
					else:
						print('Nothing to change for interface {0} (id: {1}, exit: 5)'.format(
							interface['name'], interface['id']))
						continue
				# Check for specific tags
				elif interface.get('tags', None):
					new_desc = None
					for intf_tag in interface['tags']:
						# Pickup interface with Tag: cid_XXX
						if 'cid' in intf_tag:
							form_tag = re.sub('^cid_', '', intf_tag)
							circuits = netbox_get_circuits()
							for circuit in circuits['results']:
								if circuit['cid'] == form_tag:
									cid_isp = circuit['provider']['name']
									cid_svc = circuit['type']['name']
									new_desc = 'Transit: {0} [{1}] '.format(cid_isp, cid_svc)+'{'+form_tag +'}'
					if new_desc is None:
						print('Nothing to change for interface {0} (id: {1}, exit: 6)'.format(
							interface['name'], interface['id']))
						continue
					else:
						if cur_desc != new_desc:
							choise = yes_or_no('Change interface {0} (id:{1}) description: \'{2}\' <---> \'{3}\''.format(
								interface['name'], interface['id'], cur_desc, new_desc))
							if choise:
								data_to_mod['description'] = new_desc
								netbox_modify_interface(netbox_intf_id=interface['id'], data=data_to_mod)
							else:
								continue
						else:
							print('Nothing to change for interface {0} (id: {1}, exit: 7)'.format(
								interface['name'], interface['id']))
							continue
				# else:
				# 	print('Nothing to change for interface {0} (id: {1}, exit: 7)'.format(
				# 		interface['name'], interface['id']))
				# 	continue

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def main():
	try:
		ARGS = get_cmdline()
		dev_list = list()
		if ARGS.upd_dev:
			dev_list.append(ARGS.upd_dev)
			update_device_cfg(devices=dev_list)
		elif ARGS.upd_dev_vlans:
			dev_list.append(ARGS.upd_dev_vlans)
			update_device_vlans(devices=dev_list)
		elif ARGS.upd_site_dev:
			if ARGS.upd_site_dev.lower() in netbox_get_sites():
				dev_list = netbox_get_devices(netbox_site=ARGS.upd_site_dev)
				update_device_cfg(devices=dev_list)
			else:
				raise Exception('Site \'{}\' not found!'.format(ARGS.upd_site_dev))
		elif ARGS.upd_site_vlans:
			if ARGS.upd_site_vlans.lower() in netbox_get_sites():
				dev_list = netbox_get_devices(netbox_site=ARGS.upd_site_vlans)
				update_device_vlans(devices=dev_list)
			else:
				raise Exception('Site \'{}\' not found!'.format(ARGS.upd_site_dev))
		elif ARGS.upd_dev_db:
			update_netbox_db(device=ARGS.upd_dev_db)

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


if __name__ == '__main__':
	main()
