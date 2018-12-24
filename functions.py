#!/usr/bin/env python
import sys
import os
import subprocess
import yaml
import requests
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
NETBOX_SITES = YAML_PARAMS['netbox']['url']['sites']


def yes_or_no(question):
    while "the answer is invalid!":
        reply = str(input(question+' (y/n): ')).lower().strip()
        if reply[:1].lower() == 'y':
            return True
        if reply[:1].lower() == 'n':
            return False


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


def load_cfg_with_clogin(clogin_device):
	try:
		if not clogin_device:
			raise Exception('No device specified!')

		clogin_device_cfg = './out/{0}.cfg'.format(clogin_device)

		# Add 'conf t' on the top and 'wr' on the bottom of config file
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


def netbox_get_devices(site=None):
	try:
		if not site:
			raise Exception('No site specified!')

		r = requests.get(url='{0}/{1}'.format(NETBOX_API, NETBOX_DEVICES),
			headers={'Authorization': 'Token {0}'.format(NETBOX_TOKEN)})
		r.close()
		data = r.json()

		if data['results']:
			device_list = list()
			for device in data['results']:
				if device.get('site', None):
					if device['site']['name'].lower() == site.lower():
						device_list.append(device['name'])
			return device_list
		else:
			raise Exception('{0} not found in the netbox!'.format(site))

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


def netbox_get_sites():
	try:
		r = requests.get(url='{0}/{1}/?limit=0'.format(NETBOX_API, NETBOX_SITES),
			headers={'Authorization': 'Token {0}'.format(NETBOX_TOKEN)})
		r.close()
		data = r.json()

		if data['results']:
			sites_list = list()
			for site in data['results']:
				sites_list.append(site['name'].lower())
			return sites_list
		else:
			return False

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
