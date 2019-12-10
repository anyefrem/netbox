#!/usr/bin/env python
import sys
import os
import subprocess
import yaml
import json
import requests
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
NETBOX_SITES = YAML_PARAMS['netbox']['url']['sites']
NETBOX_VLANS = YAML_PARAMS['netbox']['url']['vlans']
NETBOX_CIRCUITS = YAML_PARAMS['netbox']['url']['circuits']


def yes_or_no(question):
    while "the answer is invalid!":
        reply = str(input(question+' (y/n): ')).lower().strip()
        if reply[:1].lower() == 'y':
            return True
        if reply[:1].lower() == 'n':
            return False


def format_rate(rate=None):
	try:
		if not rate:
			raise Exception('No rate specified!')
		n = 0
		rate_labels = {0: 'Kbps', 1: 'Mbps', 2: 'Gbps'}
		while rate > 1000:
			rate //= 1000
			n += 1
		return '{0} {1}'.format(str(rate), rate_labels[n])

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def generate_cfg_from_template(tpl_file, data_dict, trim_blocks_flag=True, lstrip_blocks_flag=False):
	try:
		tpl_dir = os.path.dirname(tpl_file)
		env = Environment(loader=FileSystemLoader(tpl_dir), trim_blocks=trim_blocks_flag,
			lstrip_blocks=lstrip_blocks_flag)
		template = env.get_template(os.path.basename(tpl_file))
		return template.render(data_dict)

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def load_cfg_with_clogin(clogin_device, clogin_device_ip):
	try:
		if not clogin_device:
			raise Exception('No device specified!')

		clogin_device_cfg = './out/{0}.cfg'.format(clogin_device.lower())

		# Add 'conf t' on the top and 'end + wr' on the bottom of config file
		with open(clogin_device_cfg, 'r') as original:
			data = original.read()
		if data.split('\n')[0] != 'conf t':
			with open(clogin_device_cfg, 'w') as modified:
				modified.write('conf t\n' + '!\n' + data + 'end\n'+ 'wr\n')

		sp = subprocess.check_output("./clogin -f ./.cloginrc -x {0} {1}".format(
			clogin_device_cfg, clogin_device_ip), shell=True)

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def load_cfg_with_napalm(napalm_device, napalm_device_ip):
	try:
		if not napalm_device:
			raise Exception('No device specified!')
		elif not napalm_device_ip:
			raise Exception('No device ip specified!')

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
		device = driver(napalm_device_ip, napalm_username, napalm_password)
		device.open()
		device.load_merge_candidate(filename='./out/{0}.cfg'.format(napalm_device.lower()))
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


def load_cfg(dst_device, src_config_dict, j2_tpl):
	try:
		if not dst_device:
			raise Exception('No device specified!')
		elif not src_config_dict:
			raise Exception('No config dict provided!')
		elif not j2_tpl:
			raise Exception('No j2 tpl provided!')
		
		dst_device_ip = netbox_get_device_ip(dst_device)
		generated_config = generate_cfg_from_template(j2_tpl, src_config_dict)
		print('{0} is going to be burned by the following lines:'.format(dst_device))
		print('*****')
		print(generated_config)
		print('*****')
		if yes_or_no('ARE YOU SURE?'):
			with open('./out/{0}.cfg'.format(dst_device.lower()), 'w') as file:
				file.write(generated_config)
			print('Connecting to {0}...'.format(dst_device))
			if dst_device.lower() not in YAML_PARAMS['telnet']:
				load = load_cfg_with_napalm(napalm_device=dst_device, napalm_device_ip=dst_device_ip)
				if load:
					print('[ok] Configuration loaded successfully!')
					return True
				else:
					print('[nok] Configuration not loaded successfully!')
					return False
			else:
				# no True/False is returned by function using clogin
				load = load_cfg_with_clogin(clogin_device=dst_device, clogin_device_ip=dst_device_ip)
				print('[ok] Configuration loaded successfully!')
				return True
		else:
			print('Operation canceled!')
			return True

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def netbox_get_device_id(netbox_device=None, silent=False):
	try:
		if not netbox_device:
			raise Exception('No device specified!')

		r = requests.get(url='{0}/{1}/?name={2}'.format(NETBOX_API, NETBOX_DEVICES, netbox_device),
			headers={'Authorization': 'Token {0}'.format(NETBOX_TOKEN)})
		r.close()
		data = r.json()

		if data['results']:
			netbox_device_id = data['results'][0]['id']
			if not silent:
				print('Found {0} id: {1}\n'.format(netbox_device, netbox_device_id))
			return netbox_device_id
		else:
			raise Exception('{0} not found in the netbox!'.format(netbox_device))

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def netbox_get_device_site_id(netbox_device=None):
	try:
		if not netbox_device:
			raise Exception('No device specified!')

		r = requests.get(url='{0}/{1}/{2}'.format(NETBOX_API, NETBOX_DEVICES, netbox_get_device_id(netbox_device)),
			headers={'Authorization': 'Token {0}'.format(NETBOX_TOKEN)})
		r.close()
		data = r.json()

		if data:
			netbox_device_site_id = data['site']['id']
			return netbox_device_site_id
		else:
			raise Exception('{0} not found in the netbox!'.format(netbox_device))

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def netbox_get_device_ip(netbox_device=None):
	try:
		if not netbox_device:
			raise Exception('No device specified!')

		r = requests.get(url='{0}/{1}/{2}'.format(NETBOX_API, NETBOX_DEVICES, netbox_get_device_id(netbox_device, silent=True)),
			headers={'Authorization': 'Token {0}'.format(NETBOX_TOKEN)})
		r.close()
		data = r.json()

		if data:
			netbox_device_ip = data['primary_ip4']['address']
			return netbox_device_ip.split('/')[0]
		else:
			raise Exception('{0} not found in the netbox!'.format(netbox_device))

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def netbox_check_if_switch(netbox_device=None):
	try:
		if not netbox_device:
			raise Exception('No device specified!')

		r = requests.get(url='{0}/{1}/{2}'.format(NETBOX_API, NETBOX_DEVICES,
			netbox_get_device_id(netbox_device, silent=True)),
			headers={'Authorization': 'Token {0}'.format(NETBOX_TOKEN)})
		r.close()
		data = r.json()

		if data:
			netbox_device_role = data['device_role']['slug']
			if 'switch' in netbox_device_role:
				return True
			else:
				return False
		else:
			raise Exception('{0} not found in the netbox!'.format(netbox_device))

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def netbox_get_devices(netbox_site=None):
	try:
		if not netbox_site:
			raise Exception('No site specified!')

		r = requests.get(url='{0}/{1}'.format(NETBOX_API, NETBOX_DEVICES),
			headers={'Authorization': 'Token {0}'.format(NETBOX_TOKEN)})
		r.close()
		data = r.json()

		if data['results']:
			device_list = list()
			for device in data['results']:
				if device.get('site', None):
					if device['site']['name'].lower() == netbox_site.lower():
						device_list.append(device['name'])
			return device_list
		else:
			raise Exception('{0} not found in the netbox!'.format(netbox_site))

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def netbox_get_vlans(netbox_site_id=None):
	try:
		if not netbox_site_id:
			raise Exception('No site id specified!')

		r = requests.get(url='{0}/{1}?limit=0'.format(NETBOX_API, NETBOX_VLANS),
			headers={'Authorization': 'Token {0}'.format(NETBOX_TOKEN)})
		r.close()
		data = r.json()

		if data['results']:
			vlan_list = list()
			for vlan in data['results']:
				if vlan.get('site', None):
					if vlan['site']['id'] == netbox_site_id:
						if vlan['tags']:
							vlan_action = vlan['tags'][0]
						else:
							vlan_action = None
						vlan_list.append({
							'vlan_id': vlan['id'],
							'vlan_vid': vlan['vid'],
							'vlan_name': vlan['name'],
							'action': vlan_action
							})
			return vlan_list
		else:
			raise Exception('Site with id \'{0}\' not found in the netbox!'.format(netbox_site_id))

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


def netbox_get_circuits(circuit_url=None):
	try:
		if circuit_url:
			r = requests.get(url=circuit_url,
				headers={'Authorization': 'Token {0}'.format(NETBOX_TOKEN)})
		else:
			r = requests.get(url='{0}/{1}/?limit=0'.format(NETBOX_API, NETBOX_CIRCUITS),
				headers={'Authorization': 'Token {0}'.format(NETBOX_TOKEN)})
		r.close()
		return r.json()

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def netbox_modify_interface(netbox_intf_id=None, data=None):
	try:
		if (not netbox_intf_id) or (not data):
			raise Exception("No data is provided!")

		r = requests.patch(url='{0}/{1}/{2}/'.format(NETBOX_API, NETBOX_INTERFACES, netbox_intf_id),
			headers={'Authorization': 'Token {0}'.format(NETBOX_TOKEN)}, json=data)
		r.close()
		print('NetBox DB operation status code: {0}'.format(r.status_code))

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def netbox_modify_vlan(netbox_vlan_id=None, netbox_vlan_action=None):
	try:
		if (not netbox_vlan_id) or (not netbox_vlan_action):
			raise Exception("No data provided!")

		if netbox_vlan_action == 'vlan_add':
			r = requests.patch(url='{0}/{1}/{2}/'.format(NETBOX_API, NETBOX_VLANS, netbox_vlan_id),
				headers={'Authorization': 'Token {0}'.format(NETBOX_TOKEN)}, json={'tags':['vlan_ok']})
		elif netbox_vlan_action == 'vlan_del':
			r = requests.delete(url='{0}/{1}/{2}/'.format(NETBOX_API, NETBOX_VLANS, netbox_vlan_id),
				headers={'Authorization': 'Token {0}'.format(NETBOX_TOKEN)})

		r.close()
		print('NetBox DB operation status code: {0}'.format(r.status_code))

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def populate_vlan_list(netbox_interface=None):
	try:
		if not netbox_interface:
			raise Exception("No data provided!")

		vlan_list = list()
		native_vlan = False

		# Pickup interface with 802.1Q Mode: Tagged
		if netbox_interface.get('mode', None):
			if netbox_interface['mode']['value'] == 200:
				if netbox_interface.get('untagged_vlan', None):
					# Add native vlan to the vlan list and
					# set 'native_vlan' in case when native vlan id is not '1'
					vlan_list.append(netbox_interface['untagged_vlan']['vid'])
					if netbox_interface['untagged_vlan']['vid'] != 1:
						native_vlan = netbox_interface['untagged_vlan']['vid']

				for vlan in netbox_interface['tagged_vlans']:
					vlan_list.append(vlan['vid'])

		return native_vlan, vlan_list

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)
