#!/usr/bin/env python

import sys
import os
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
	parser.add_argument('-i2', dest='upd_dev_site', type=str,
							help='update interface descriptions on every device across a whole site',
							required=False)
	parser.add_argument('-i3', dest='upd_dev_db', type=str,
							help='update interface descriptions of a single device in netbox',
							required=False)
	parser.add_argument('-v1', dest='upd_dev_vlans', type=str,
							help='update vlans on a single device',
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
				# Result dictionary defaults
				intf_tags = ['gw', 'isp_l2', 'isp_l3', 'upd_on_dev']
				vlan_list = list()
				native_vlan = False
				isp_l2_flag = False
				isp_l3_flag = False
				populate_flag = False
				if interface['device']['id'] == NETBOX_DEVICE_ID:
					# Pickup connected interface
					if interface['is_connected']:
						# print(interface['id'])
						# Pickup interface with 802.1Q Mode: Tagged
						if interface.get('mode', None):
							if interface['mode']['value'] == 200:
								if interface.get('untagged_vlan', None):
									# Add native vlan to the vlan list and
									# set 'native_vlan' in case when native vlan id is not '1'
									vlan_list.append(interface['untagged_vlan']['vid'])
									if interface['untagged_vlan']['vid'] != 1:
										native_vlan = interface['untagged_vlan']['vid']
								for vlan in interface['tagged_vlans']:
									vlan_list.append(vlan['vid'])
						populate_flag = True
					# Pickup interfaces tagged with predefined tags (intf_tags).
					# N.B. Tag 'upd_on_dev' is when an interface's description is not being
					# automatically updated in Netbox (manually binded),
					# but is being replicated from Netbox to a device
					elif check_intf_tags:
						for item in intf_tags:
							if item in check_intf_tags:
								if item == 'isp_l2':
									isp_l2_flag = True
								elif item == 'isp_l3':
									isp_l3_flag = True
								populate_flag = True
					# Populate resulting list of interfaces
					if populate_flag:
						intf_list.append({
						'name': interface['name'],
						'desc': interface['description'],
						'vlans': vlan_list,
						'native_vlan': native_vlan,
						'isp_l2_flag': isp_l2_flag,
						'isp_l3_flag': isp_l3_flag,
						'mtu': mtu,
						'mss': mss
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

		vlans_add = list()
		vlans_del = list()
		config_dict = dict()

		for device in devices:
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
					for vlan in vlans_add:
						netbox_modify_vlan(netbox_vlan_id=vlan['id'], netbox_vlan_action='vlan_add')
					for vlan in vlans_del:
						netbox_modify_vlan(netbox_vlan_id=vlan['id'], netbox_vlan_action='vlan_del')
			else:
				print('No vlans need to be modified!')


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
				# Pickup connected interfaces
				if interface['is_connected']:
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
				# Pickup interfaces with 802.1Q Mode: Access
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
				else:
					print('Nothing to change for interface {0} (id: {1}, exit: 6)'.format(
						interface['name'], interface['id']))
					continue

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
		elif ARGS.upd_dev_site:
			if ARGS.upd_dev_site.lower() in netbox_get_sites():
				dev_list = netbox_get_devices(netbox_site=ARGS.upd_dev_site)
				update_device_cfg(devices=dev_list)
			else:
				raise Exception('Site \'{}\' not found!'.format(ARGS.upd_dev_site))
		elif ARGS.upd_dev_db:
			update_netbox_db(device=ARGS.upd_dev_db)

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


if __name__ == '__main__':
	main()
