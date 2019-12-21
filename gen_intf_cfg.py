#!/usr/bin/env python

import sys
import os
import re
import yaml
import requests
import argparse
import pynetbox
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

NETBOX_URL = YAML_PARAMS['netbox']['url']
NETBOX_TOKEN = YAML_PARAMS['netbox']['token']
NETBOX_DEVICES = YAML_PARAMS['netbox']['inv']['devices']
NETBOX_INTERFACES = YAML_PARAMS['netbox']['inv']['interfaces']
NETBOX_SITES = YAML_PARAMS['netbox']['inv']['sites']
NETBOX_VLANS = YAML_PARAMS['netbox']['inv']['vlans']
NETBOX_CIRCUITS = YAML_PARAMS['netbox']['inv']['circuits']
NETBOX_API = pynetbox.api(NETBOX_URL, token='45243879f01dbf9b61a33468823864937497c855')
LLDP_INCOMPATIBLE_SLUGS = YAML_PARAMS['lldp_incompatible_slugs']


def get_cmdline():
	parser = argparse.ArgumentParser()
	parser.add_argument('-i1', dest='upd_dev', type=str,
							help='update interfaces description on a single device. specify a single DEVICE name from netbox, or comma separated LIST.',
							required=False)
	parser.add_argument('-i2', dest='upd_site_devs', type=str,
							help='update interfaces description across a whole site. specify a SITE name from netbox.',
							required=False)
	parser.add_argument('-i3', dest='upd_db_dev', type=str,
							help='update interfaces description of a single device in the netbox db. specify a DEVICE name from netbox.',
							required=False)
	parser.add_argument('-v1', dest='upd_dev_vlans', type=str,
							help='update vlans on a single device. specify a single DEVICE name from netbox, or comma separated LIST.',
							required=False)
	parser.add_argument('-v3', dest='upd_site_vlans', type=str,
							help='update vlans across a whole site. specify a SITE name from netbox.',
							required=False)
	parser.add_argument('-c', dest='site_circuits', type=str, nargs='?', const='all',
							help='print circuits id. specify TYPE (separated by comma if many) or leave blank for ALL.',
							required=False)
	arguments = parser.parse_args()
	return arguments


def update_device_cfg(devices=None):
	try:
		if not devices:
			raise Exception('No device(s) specified!')

		for item in devices:
			
			device = str(item)
			
			if NETBOX_API.dcim.devices.get(name=device) is None:
				print('{0} not found in the netbox!'.format(device))
				sys.exit(1)
			else:
				NETBOX_DEVICE_VIEW = NETBOX_API.dcim.devices.get(name=device)
				NETBOX_DEVICE_ID = NETBOX_DEVICE_VIEW.id
				NETBOX_DEVICE_IP = str(NETBOX_DEVICE_VIEW.primary_ip4).split('/')[0]
				NETBOX_DEVICE_MODEL = str(NETBOX_DEVICE_VIEW.device_type.slug)
				NETBOX_DEVICE_INTFS = NETBOX_API.dcim.interfaces.filter(device=device)
				print('Found {0} id: {1}\n'.format(device, NETBOX_DEVICE_ID))

			config_dict = dict()
			intf_list = list()
			intf_tags = ['gw', 'isp_l2', 'isp_l3', 'upd_desc', 'upd_trunk']

			for interface in NETBOX_DEVICE_INTFS:
				check_intf_tags = interface.tags
				# MTU, MSS
				if interface.mtu:
					mtu = interface.mtu
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
				circuit_isp = False
				circuit_svc = False
				circuit_rate = False
				switch_flag = False
				lldp_flag = False
				populate_flag = False

				# Pickup connected interface or LAG
				if interface.interface_connection or 'LAG' in interface.form_factor.label:
					# print(interface.name)
					pvl = populate_vlan_list(interface)
					print(pvl)
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
							cid_url = '{0}/api/{1}/{2}'.format(NETBOX_URL, NETBOX_CIRCUITS, re.sub('^cid_', '', intf_tag))
							circuit = netbox_get_circuits(cid_url)
							circuit_isp = circuit['provider']['name']
							circuit_svc = circuit['type']['name']
							# kbps -> bps
							circuit_rate = int(circuit['commit_rate'])*1000
					for item in intf_tags:
						if item in check_intf_tags:
							if item == 'isp_l2':
								isp_l2_flag = True
								if 'switch' in NETBOX_DEVICE_VIEW.device_role.slug:
									switch_flag = True
									if interface.mode:
										if interface.mode.value == 100:
											access_vlan = interface.untagged_vlan.vid
								elif NETBOX_DEVICE_MODEL not in LLDP_INCOMPATIBLE_SLUGS:
									lldp_flag = True
							elif item == 'isp_l3':
								isp_l3_flag = True
							elif item == 'upd_trunk':
								pvl = populate_vlan_list(interface)
								native_vlan = pvl[0]
								vlan_list = pvl[1]
							populate_flag = True

				if populate_flag:
					intf_list.append({
					'name': interface.name,
					'desc': interface.description,
					'vlans': vlan_list,
					'native_vlan': native_vlan,
					'access_vlan': access_vlan,
					'isp_l2_flag': isp_l2_flag,
					'isp_l3_flag': isp_l3_flag,
					'mtu': mtu,
					'mss': mss,
					'circuit_isp': circuit_isp,
					'circuit_svc': circuit_svc,
					'circuit_rate': circuit_rate,
					'switch_flag': switch_flag,
					'lldp_flag': lldp_flag
					})

			config_dict['interfaces'] = intf_list

			# Load config on device
			# pprint(config_dict)
			# sys.exit(1)
			load_cfg(dst_device=device, dst_device_ip=NETBOX_DEVICE_IP, src_config_dict=config_dict, j2_tpl='./out/tpl_intf.j2')

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

		for item in devices:

			device = str(item)

			if NETBOX_API.dcim.devices.get(name=device) is None:
				print('{0} not found in the netbox!'.format(device))
				if device == devices[-1]:
					sys.exit(1)
				else:
					continue
			else:
				NETBOX_DEVICE_VIEW = NETBOX_API.dcim.devices.get(name=device)

			if 'switch' not in NETBOX_DEVICE_VIEW.device_role.slug:
				print('Skipping {0}'.format(device))
				continue
			else:
				sw_count += 1
				vlans_add = list()
				vlans_del = list()
				config_dict = dict()

			vlans = netbox_get_vlans(netbox_site_id=NETBOX_DEVICE_VIEW.site.id)

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

		if (sw_count > 0) and (ok_count == sw_count):
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
		
		# NETBOX_DEVICE_ID = netbox_get_device_id(netbox_device=device)
		if NETBOX_API.dcim.devices.get(name=device) is None:
			print('{0} not found in the netbox!'.format(device))
			sys.exit(1)
		else:
			NETBOX_DEVICE_VIEW = NETBOX_API.dcim.devices.get(name=device)
			NETBOX_DEVICE_ID = NETBOX_DEVICE_VIEW.id
			print('Found {0} id: {1}\n'.format(device, NETBOX_DEVICE_ID))

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
				elif interface.get('mode', None) and interface['circuit_termination'] is None and 'gw' in interface['tags']:
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
				# Pickup router's interface with circuit termination
				# elif interface['circuit_termination'] and not netbox_check_if_switch(device):
				elif interface['circuit_termination'] and 'switch' not in NETBOX_API.dcim.devices.get(name=device).device_role.slug:
					circuit = netbox_get_circuits(interface['circuit_termination']['circuit']['url'])
					circuit_isp = circuit['provider']['name']
					circuit_svc = circuit['type']['name']
					circuit_rate = int(circuit['commit_rate'])
					form_circuit_rate = format_rate(circuit_rate)
					new_desc = 'Transit: {0} [{1}] '.format(
									circuit_isp, form_circuit_rate)+'{'+circuit['cid'] +'}'+' ({0})'.format(circuit_svc)
					if cur_desc != new_desc:
						choise = yes_or_no('Change interface {0} (id:{1}) description: \'{2}\' <---> \'{3}\''.format(
							interface['name'], interface['id'], cur_desc, new_desc))
						if choise:
							if 'cid_' + str(circuit['id']) not in interface['tags']:
								interface['tags'].append('cid_' + str(circuit['id']))
								data_to_mod['tags'] = interface['tags']
							data_to_mod['description'] = new_desc
							netbox_modify_interface(netbox_intf_id=interface['id'], data=data_to_mod)
						continue
					else:
						print('Nothing to change for interface {0} (id: {1}, exit: 6)'.format(
							interface['name'], interface['id']))
						continue
				# Check for specific tags
				elif interface.get('tags', None):
					new_desc = None
					for intf_tag in interface['tags']:
						# Pickup interface with Tag: cid_XXX (but without direct circuit termination!)
						if 'cid' in intf_tag:
							cid_url = '{0}/api/{1}/{2}'.format(NETBOX_URL, NETBOX_CIRCUITS, re.sub('^cid_', '', intf_tag))
							circuit = netbox_get_circuits(cid_url)
							circuit_cid = circuit['cid']
							circuit_isp = circuit['provider']['name']
							circuit_svc = circuit['type']['name']
							circuit_rate = int(circuit['commit_rate'])
							form_circuit_rate = format_rate(circuit_rate)
							new_desc = 'Transit: {0} [{1}] '.format(
								circuit_isp, form_circuit_rate)+'{'+circuit_cid +'}'+' ({0})'.format(circuit_svc)
					if new_desc is None:
						print('Nothing to change for interface {0} (id: {1}, exit: 7)'.format(
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
							print('Nothing to change for interface {0} (id: {1}, exit: 8)'.format(
								interface['name'], interface['id']))
							continue
				# else:
				# 	print('Nothing to change for interface {0} (id: {1}, exit: 9)'.format(
				# 		interface['name'], interface['id']))
				# 	continue

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def circuits_info(types=None):
	try:
		if not types:
			raise Exception('No types specified!')
		c_info = netbox_get_circuits()
		for circuit in c_info['results']:
			if circuit['type']['slug'] in types or types == 'all':
				print('isp: {0}, type: {1}, cid: {2}, id: {3}'.format(
					circuit['provider']['name'], circuit['type']['slug'], circuit['cid'], circuit['id']))

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
			dev_list = ARGS.upd_dev.split(',')
			update_device_cfg(devices=dev_list)

		elif ARGS.upd_dev_vlans:
			dev_list = ARGS.upd_dev_vlans.split(',')
			update_device_vlans(devices=dev_list)

		elif ARGS.upd_site_devs:
			if ARGS.upd_site_devs.lower() in netbox_get_sites():
				dev_list = NETBOX_API.dcim.devices.filter(site=ARGS.upd_site_devs.lower())
				update_device_cfg(devices=dev_list)
			else:
				raise Exception('Site \'{}\' not found!'.format(ARGS.upd_site_devs))

		elif ARGS.upd_site_vlans:
			if ARGS.upd_site_vlans.lower() in netbox_get_sites():
				dev_list = NETBOX_API.dcim.devices.filter(site=ARGS.upd_site_vlans.lower())
				update_device_vlans(devices=dev_list)
			else:
				raise Exception('Site \'{}\' not found!'.format(ARGS.upd_site_dev))

		elif ARGS.upd_db_dev:
			update_netbox_db(device=ARGS.upd_db_dev)

		elif ARGS.site_circuits:
			if ARGS.site_circuits is not 'all':
				types = ARGS.site_circuits.split(',')
				circuits_info(types)
			else:
				circuits_info(ARGS.site_circuits)

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


if __name__ == '__main__':
	main()
