#!/usr/bin/env python

import sys
import os
import subprocess
import yaml
import requests
import argparse
from pprint import pprint
from jinja2 import Environment, FileSystemLoader
from napalm import get_network_driver


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


def yes_or_no(question):
    while "the answer is invalid!":
        reply = str(input(question+' (y/n): ')).lower().strip()
        if reply[:1].lower() == 'y':
            return True
        if reply[:1].lower() == 'n':
            return False


def get_cmdline():
	parser = argparse.ArgumentParser()
	parser.add_argument('-d', dest='device', help='update interface descriptions on a device', required=False, action='store_true')
	parser.add_argument('-u', dest='update', help='update interface descriptions in the netbox', required=False, action='store_true')
	parser.add_argument('-n', type=str, dest='name', help='name of a device (the same as in the netbox)', required=True)
	arguments = parser.parse_args()
	return arguments


def generate_cfg_from_template(tpl_file, data_dict, trim_blocks_flag=True, lstrip_blocks_flag=False):
	try:
		tpl_dir = os.path.dirname(tpl_file)
		env = Environment(loader=FileSystemLoader(tpl_dir), trim_blocks=trim_blocks_flag, lstrip_blocks=lstrip_blocks_flag)
		template = env.get_template(os.path.basename(tpl_file))
		return template.render(data_dict)

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def load_cfg_with_napalm(napalm_device):
	try:
		if not napalm_device:
			raise Exception('No device specified!')

		check_device = YAML_PARAMS['napalm'].get(napalm_device, None)

		if check_device:
			napalm_driver = YAML_PARAMS['napalm'][napalm_device]['driver']
			napalm_username = YAML_PARAMS['napalm'][napalm_device]['username']
			napalm_password = YAML_PARAMS['napalm'][napalm_device]['password']
		else:
			napalm_driver = YAML_PARAMS['napalm']['default']['driver']
			napalm_username = YAML_PARAMS['napalm']['default']['username']
			napalm_password = YAML_PARAMS['napalm']['default']['password']

		driver = get_network_driver(napalm_driver)
		device = driver(napalm_device, napalm_username, napalm_password)
		device.open()
		device.load_merge_candidate(filename='./out/{0}.cfg'.format(napalm_device))
		diffs = device.compare_config()
		print('Diff by NAPALM:')
		print('*****')
		if diffs:
			print(diffs)
			print('*****')
		else:
			print('Empty!')
			print('*****')
			return True
		if yes_or_no('ARE YOU STILL SURE?'):
			 device.commit_config()
			 return True
		else:
			return False

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def load_cfg_with_clogin(clogin_device):
	try:
		if not clogin_device:
			raise Exception('No device specified!')

		clogin_device_cfg = './out/{0}.cfg'.format(clogin_device)

		with open(clogin_device_cfg, 'r') as original:
			data = original.read()
		if data.split('\n')[0] != 'conf t':
			with open(clogin_device_cfg, 'w') as modified:
				modified.write('conf t\n' + '!\n' + data + '\nwr')

		sp = subprocess.check_output("./clogin -x {0} {1}".format(clogin_device_cfg, clogin_device), shell=True)

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def netbox_get_device_id(device=None):
	try:
		if not device:
			raise Exception('No device specified!')

		r = requests.get(url='{0}/{1}/?name={2}'.format(NETBOX_API, NETBOX_DEVICES, device),
			headers={'Authorization': 'Token {0}'.format(NETBOX_TOKEN)})
		r.close()
		data = r.json()

		if data['results']:
			device_id = data['results'][0]['id']
			print('Found {0} id: {1}\n'.format(device, device_id))
			return device_id
		else:
			raise Exception('{0} not found in the netbox!'.format(device))

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def netbox_get_interfaces():
	try:
		r = requests.get(url='{0}/{1}/?limit=0'.format(NETBOX_API, NETBOX_INTERFACES),
			headers={'Authorization': 'Token {0}'.format(NETBOX_TOKEN)})
		r.close()
		return r.json()

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def netbox_modify_interface(intf_id=None, data=None):
	try:
		if (not intf_id) or (not data):
			raise Exception("No data is provided!")

		r = requests.patch(url='{0}/{1}/{2}/'.format(NETBOX_API, NETBOX_INTERFACES, intf_id),
			headers={'Authorization': 'Token {0}'.format(NETBOX_TOKEN)}, data=data)
		r.close()
		print('Operation status code: {0}'.format(r.status_code))

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def netbox_update_device_cfg(device=None):
	try:
		if not device:
			raise Exception('No device specified!')

		NETBOX_DEVICE_ID = netbox_get_device_id(device)

		data = netbox_get_interfaces()

		# Populate config dictionary
		config_dict = dict()
		intf_list = list()
		
		for interface in data['results']:
			check_intf_tag = interface.get('tags', None)
			vlan_list = list()
			if interface['device']['id'] == NETBOX_DEVICE_ID:
				if interface['is_connected']:
					# print(interface['id'])
					if interface.get('mode', None):
						if interface['mode']['value'] == 200:
							if interface.get('untagged_vlan', None):
								vlan_list.append(interface['untagged_vlan']['vid'])
								if interface['untagged_vlan']['vid'] != 1:
									native_vlan = interface['untagged_vlan']['vid']
								else:
									native_vlan = False
							else:
								native_vlan = False
							for vlan in interface['tagged_vlans']:
								vlan_list.append(vlan['vid'])
						else:
							native_vlan = False
					else:
						native_vlan = False
					intf_list.append({
						'name': interface['name'],
						'desc': interface['description'],
						'vlans': vlan_list,
						'native_vlan': native_vlan
						})
				elif ('upd_on_dev' in check_intf_tag) or ('gw' in check_intf_tag):
					intf_list.append({
						'name': interface['name'],
						'desc': interface['description'],
						'vlans': vlan_list,
						'native_vlan': False
						})

		config_dict['interfaces'] = intf_list
		
		# Load config on device
		# pprint(config_dict)
		# sys.exit(1)
		generated_config = generate_cfg_from_template('./out/template.j2',config_dict)
		print('{0} is going to be burned by the following lines:'.format(device))
		print('*****')
		print(generated_config)
		print('*****')
		
		if yes_or_no('ARE YOU SURE?'):
			with open('./out/{0}.cfg'.format(device.lower()), 'w') as file:
				file.write(generated_config)
			print('Connecting to {0}...'.format(device))
			if device.lower() not in YAML_PARAMS['telnet']:
				load_cfg_with_napalm(device.lower())
			else:				
				load_cfg_with_clogin(device.lower())

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def netbox_update_db(device=None):
	try:
		if not device:
			raise Exception('No device specified!')
		
		NETBOX_DEVICE_ID = netbox_get_device_id(device)

		data = netbox_get_interfaces()

		for interface in data['results']:
			cur_desc = interface['description']
			data_to_mod = dict()
			if interface['device']['id'] == NETBOX_DEVICE_ID:
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
							netbox_modify_interface(interface['id'], data_to_mod)
					elif (not static_desc) and (cur_desc != new_desc):
						choise = yes_or_no('Change interface {0} (id: {1}) description: \'{2}\' <---> \'{3}\''.format(
							interface['name'], interface['id'], cur_desc, new_desc))
						if choise:
							data_to_mod['description'] = new_desc
							netbox_modify_interface(interface['id'], data_to_mod)
					else:
						print('Nothing to change for interface {0} (id: {1}, exit: 1)'.format(interface['name'], interface['id']))
						continue
				elif interface.get('mode', None):
					if (interface['mode']['value'] == 100) and (interface.get('tags', None)):
						if 'gw' in interface['tags']:
							if interface.get('untagged_vlan', None):
								new_desc = 'Gateway: VLAN {0}'.format(interface['untagged_vlan']['vid'])
							else:
								print('Nothing to change for interface {0} (id: {1}, exit: 2)'.format(interface['name'], interface['id']))
								continue
							if cur_desc != new_desc:
								choise = yes_or_no('Change interface {0} (id:{1}) description: \'{2}\' <---> \'{3}\''.format(
									interface['name'], interface['id'], cur_desc, new_desc))
								if choise:
									data_to_mod['description'] = new_desc
									netbox_modify_interface(interface['id'], data_to_mod)
								else:
									continue
							else:
								print('Nothing to change for interface {0} (id: {1}, exit: 3)'.format(interface['name'], interface['id']))
								continue
						else:
							print('Nothing to change for interface {0} (id: {1}, exit: 4)'.format(interface['name'], interface['id']))
							continue
					else:
						print('Nothing to change for interface {0} (id: {1}, exit: 5)'.format(interface['name'], interface['id']))
						continue
				else:
					print('Nothing to change for interface {0} (id: {1}, exit: 6)'.format(interface['name'], interface['id']))
					continue

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def main():
	try:
		ARGS = get_cmdline()
		if (not ARGS.device) and (not ARGS.update):
			raise Exception('Please use either -d or -u! (neither is used)')
		elif (ARGS.device and ARGS.update):
			raise Exception('Please use either -d or -u! (both is used)')
		elif ARGS.device:
			netbox_update_device_cfg(ARGS.name)
		elif ARGS.update:
			netbox_update_db(ARGS.name)

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


if __name__ == '__main__':
	main()
