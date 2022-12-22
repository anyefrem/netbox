import sys
import os
import re
# import yaml
# import requests
import argparse
# import pynetbox

from pprint import pprint

# Local functions.py
from functions import *


# if os.path.exists('./config.yml'):
# 	with open('./config.yml') as f:
# 		YAML_PARAMS = yaml.safe_load(f)
# 		f.close()
# else:
# 	print('config.yml not found!')
# 	sys.exit(1)

# NETBOX_URL = YAML_PARAMS['netbox']['url']
# NETBOX_TOKEN = YAML_PARAMS['netbox']['token']
# NETBOX_API = pynetbox.api(NETBOX_URL, token=NETBOX_TOKEN)
# LLDP_INCOMPATIBLE_SLUGS = YAML_PARAMS['lldp_incompatible_slugs']


def get_cmdline():
	parser = argparse.ArgumentParser()
	parser.add_argument('-i1', dest='upd_dev', type=str,
							help='update interface descriptions on a single device. specify a single DEVICE name from netbox, or comma separated LIST.',
							required=False)
	parser.add_argument('-i2', dest='upd_site_devs', type=str,
							help='update interface descriptions across a whole site. specify a single SITE name from netbox, or comma separated LIST.',
							required=False)
	parser.add_argument('-i3', dest='upd_db_dev', type=str,
							help='update interface descriptions of a single device in the netbox db. specify a DEVICE name from netbox, \
							or comma separated LIST.',
							required=False)
	parser.add_argument('-v1', dest='upd_dev_vlans', type=str,
							help='update vlans on a single device. specify a single DEVICE name from netbox, or comma separated LIST.',
							required=False)
	parser.add_argument('-v2', dest='upd_site_vlans', type=str,
							help='update vlans across a whole site. specify a SITE name from netbox, or comma separated LIST.',
							required=False)
	parser.add_argument('-v3', dest='upd_dev_vlans_desc', type=str,
							help='update vlans description on a single device. specify a single DEVICE name from netbox, or comma separated LIST.',
							required=False)
	parser.add_argument('-v4', dest='upd_site_vlans_desc', type=str,
							help='update vlans description across a whole site. specify a SITE name from netbox, or comma separated LIST.',
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
				NETBOX_DEVICE_TAGS = NETBOX_DEVICE_VIEW.tags
				print('Found {0} id: {1}\n'.format(device, NETBOX_DEVICE_ID))

			if 'down' in NETBOX_DEVICE_TAGS:
				print('{0} is tagged as DOWN, skipping..'.format(device))
				continue

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

				#
				# Pickup connected interface or LAG
				#
				if interface.interface_connection or 'LAG' in interface.form_factor.label:
					# print(interface.name)
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
							circuit = NETBOX_API.circuits.circuits.get(re.sub('^cid_', '', intf_tag))
							circuit_isp = circuit.provider.name
							circuit_svc = circuit.type.name
							# kbps -> bps
							circuit_rate = int(circuit.commit_rate)*1000
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
				NETBOX_DEVICE_IP = str(NETBOX_DEVICE_VIEW.primary_ip4).split('/')[0]
				NETBOX_DEVICE_TAGS = NETBOX_DEVICE_VIEW.tags

			if 'switch' not in NETBOX_DEVICE_VIEW.device_role.slug:
				print('Skipping {0}'.format(device))
				continue
			elif 'down' in NETBOX_DEVICE_TAGS:
				print('{0} is tagged as DOWN, skipping..'.format(device))
				continue
			else:
				sw_count += 1
				vlans_add = list()
				vlans_del = list()
				config_dict = dict()

			site_vlans = NETBOX_API.ipam.vlans.filter(site_id=NETBOX_DEVICE_VIEW.site.id)

			for vlan in site_vlans:
				if vlan.tags:
					if vlan.tags[0] == 'vlan_add':
						# 'id' - ID in netbox, 'vid' - VLAN ID
						vlans_add.append({
							'id': vlan.id,
							'vid': vlan.vid,
							'name': vlan.name
							})
					elif vlan.tags[0] == 'vlan_del':
						vlans_del.append({
							'id': vlan.id,
							'vid': vlan.vid,
							'name': vlan.name
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
				if load_cfg(dst_device=device, dst_device_ip=NETBOX_DEVICE_IP, src_config_dict=config_dict, j2_tpl='./out/tpl_vlan.j2'):
					ok_count += 1
			else:
				print('{0}: no vlans need to be modified!'.format(device))

		if (sw_count > 0) and (ok_count == sw_count):
			for item in vlans_add:
				vlan = NETBOX_API.ipam.vlans.get(item['id'])
				oper = vlan.update({'tags':['vlan_ok']})
				print('Operation returned status: {0}'.format(oper))
			for item in vlans_del:
				vlan = NETBOX_API.ipam.vlans.get(item['id'])
				oper = vlan.delete()
				print('Operation returned status: {0}'.format(oper))

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def update_device_vlans_desc(devices=None):
	try:
		if not devices:
			raise Exception('No device specified!')

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
				NETBOX_DEVICE_IP = str(NETBOX_DEVICE_VIEW.primary_ip4).split('/')[0]
				NETBOX_DEVICE_TAGS = NETBOX_DEVICE_VIEW.tags

			if 'switch' not in NETBOX_DEVICE_VIEW.device_role.slug:
				print('Skipping {0}'.format(device))
				continue
			elif 'down' in NETBOX_DEVICE_TAGS:
				print('{0} is tagged as DOWN, skipping..'.format(device))
				continue
			else:
				vlans_add = list()
				config_dict = dict()

			site_vlans = NETBOX_API.ipam.vlans.filter(site_id=NETBOX_DEVICE_VIEW.site.id)

			for vlan in site_vlans:
				vlans_add.append({
					'vid': vlan.vid,
					'name': vlan.name
					})

			if vlans_add:
				config_dict['vlans_add'] = vlans_add
			else:
				config_dict['vlans_add'] = None

			if config_dict:
				load_cfg(dst_device=device, dst_device_ip=NETBOX_DEVICE_IP, src_config_dict=config_dict, j2_tpl='./out/tpl_vlan.j2')

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)


def update_netbox_db(device=None):
	try:
		if not device:
			raise Exception('No device specified!')

		if NETBOX_API.dcim.devices.get(name=device) is None:
			print('{0} not found in the netbox!'.format(device))
			sys.exit(1)
		else:
			NETBOX_DEVICE_VIEW = NETBOX_API.dcim.devices.get(name=device)
			NETBOX_DEVICE_ID = NETBOX_DEVICE_VIEW.id
			NETBOX_DEVICE_INTFS = NETBOX_API.dcim.interfaces.filter(device=device)
			print('Found {0} id: {1}\n'.format(device, NETBOX_DEVICE_ID))

		static_desc_dict = YAML_PARAMS['netbox']['static_intf_desc']

		for interface in NETBOX_DEVICE_INTFS:
			cur_desc = interface.description
			static_desc = static_desc_dict.get(interface.id, None)
			data_to_mod = dict()
			#
			# Pickup interface connected to another device (but not circuit termination)
			#
			if interface.is_connected and interface.interface_connection:
				connected_to_dev = interface.interface_connection.interface.device.name
				connected_to_intf = interface.interface_connection.interface.name
				new_desc = 'Core: {0} {1}'.format(connected_to_dev.lower(), connected_to_intf)
				if static_desc and (cur_desc != static_desc):
					choise = yes_or_no('Change interface {0} (id:{1}) description: \'{2}\' <---> \'{3}\''.format(
						interface.name, interface.id, cur_desc, static_desc))
					if choise:
						data_to_mod['description'] = static_desc
						oper = interface.update(data_to_mod)
						print('Operation returned status: {0}'.format(oper))
				elif (not static_desc) and (cur_desc != new_desc):
					choise = yes_or_no('Change interface {0} (id: {1}) description: \'{2}\' <---> \'{3}\''.format(
						interface.name, interface.id, cur_desc, new_desc))
					if choise:
						data_to_mod['description'] = new_desc
						oper = interface.update(data_to_mod)
						print('Operation returned status: {0}'.format(oper))
				else:
					print('Nothing to change for interface {0} (id: {1}, exit: 1)'.format(
						interface.name, interface.id))
					continue
			#
			# Pickup interface with 802.1Q Mode: Access
			#
			elif interface.mode and (interface.circuit_termination is None) and ('gw' in interface.tags):
				if (interface.mode.value == 100) and (interface.tags):
					# ..and tagged 'gw'
					if 'gw' in interface.tags:
						if interface.untagged_vlan:
							new_desc = 'Gateway: VLAN {0} ({1})'.format(interface.untagged_vlan.vid, interface.untagged_vlan)
						else:
							print('Nothing to change for interface {0} (id: {1}, exit: 2)'.format(
								interface.name, interface.id))
							continue
						if static_desc and (cur_desc != static_desc):
							choise = yes_or_no('Change interface {0} (id:{1}) description: \'{2}\' <---> \'{3}\''.format(
								interface.name, interface.id, cur_desc, static_desc))
							if choise:
								data_to_mod['description'] = static_desc
								oper = interface.update(data_to_mod)
								print('Operation returned status: {0}'.format(oper))
						elif (not static_desc) and (cur_desc != new_desc):
							choise = yes_or_no('Change interface {0} (id: {1}) description: \'{2}\' <---> \'{3}\''.format(
								interface.name, interface.id, cur_desc, new_desc))
							if choise:
								data_to_mod['description'] = new_desc
								oper = interface.update(data_to_mod)
								print('Operation returned status: {0}'.format(oper))
						else:
							print('Nothing to change for interface {0} (id: {1}, exit: 3)'.format(
								interface.name, interface.id))
							continue
					else:
						print('Nothing to change for interface {0} (id: {1}, exit: 4)'.format(
							interface.name, interface.id))
						continue
				else:
					print('Nothing to change for interface {0} (id: {1}, exit: 5)'.format(
						interface.name, interface.id))
					continue
			#
			# Pickup router's interface with circuit termination
			#
			elif (interface.circuit_termination) and ('switch' not in NETBOX_API.dcim.devices.get(name=device).device_role.slug):
				circuit = NETBOX_API.circuits.circuits.get(interface.circuit_termination.circuit.id)
				circuit_isp = circuit.provider.name
				circuit_svc = circuit.type.name
				circuit_rate = int(circuit.commit_rate)
				form_circuit_rate = format_rate(circuit_rate)
				new_desc = 'Transit: {0} [{1}] '.format(
								circuit_isp, form_circuit_rate)+'{'+circuit.cid +'}'+' ({0})'.format(circuit_svc)
				if cur_desc != new_desc:
					choise = yes_or_no('Change interface {0} (id:{1}) description: \'{2}\' <---> \'{3}\''.format(
						interface.name, interface.id, cur_desc, new_desc))
					if choise:
						if 'cid_' + str(circuit.id) not in interface.tags:
							interface.tags.append('cid_' + str(circuit.id))
							data_to_mod['tags'] = interface.tags
						data_to_mod['description'] = new_desc
						oper = interface.update(data_to_mod)
						print('Operation returned status: {0}'.format(oper))
					continue
				else:
					print('Nothing to change for interface {0} (id: {1}, exit: 6)'.format(
						interface.name, interface.id))
					continue
			#
			# Check for specific tags
			#
			elif interface.tags:
				new_desc = None
				for intf_tag in interface.tags:
					# Pickup interface with Tag: cid_XXX (but without direct circuit termination!)
					if 'cid' in intf_tag:
						circuit = NETBOX_API.circuits.circuits.get(re.sub('^cid_', '', intf_tag))
						circuit_cid = circuit.cid
						circuit_isp = circuit.provider.name
						circuit_svc = circuit.type.name
						circuit_rate = int(circuit.commit_rate)
						form_circuit_rate = format_rate(circuit_rate)
						new_desc = 'Transit: {0} [{1}] '.format(
							circuit_isp, form_circuit_rate)+'{'+circuit_cid +'}'+' ({0})'.format(circuit_svc)
				if new_desc is None:
					print('Nothing to change for interface {0} (id: {1}, exit: 7)'.format(
						interface.name, interface.id))
					continue
				else:
					if cur_desc != new_desc:
						choise = yes_or_no('Change interface {0} (id:{1}) description: \'{2}\' <---> \'{3}\''.format(
							interface.name, interface.id, cur_desc, new_desc))
						if choise:
							data_to_mod['description'] = new_desc
							oper = interface.update(data_to_mod)
							print('Operation returned status: {0}'.format(oper))
						else:
							continue
					else:
						print('Nothing to change for interface {0} (id: {1}, exit: 8)'.format(
							interface.name, interface.id))
						continue
			# else:
			# 	print('Nothing to change for interface {0} (id: {1}, exit: 9)'.format(
			# 		interface.name, interface.id))
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
		cir_list = NETBOX_API.circuits.circuits.all()
		for circuit in cir_list:
			if circuit.type.slug in types or types == 'all':
				print('isp: {0}, type: {1}, cid: {2}, id: {3}'.format(
					circuit.provider.name, circuit.type.slug, circuit.cid, circuit.id))

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

		elif ARGS.upd_dev_vlans or ARGS.upd_dev_vlans_desc:
			if ARGS.upd_dev_vlans:
				dev_list = ARGS.upd_dev_vlans.split(',')
				update_device_vlans(devices=dev_list)
			else:
				dev_list = ARGS.upd_dev_vlans_desc.split(',')
				update_device_vlans_desc(devices=dev_list)

		elif ARGS.upd_site_devs:
			site_list = ARGS.upd_site_devs.split(',')
			for site in site_list:
				if NETBOX_API.dcim.sites.get(name=site) or NETBOX_API.dcim.sites.get(name=site.upper()) \
					or NETBOX_API.dcim.sites.get(name=site.lower()):
					dev_list = NETBOX_API.dcim.devices.filter(site=site.lower())
					update_device_cfg(devices=dev_list)
				else:
					raise Exception('Site \'{}\' not found!'.format(ARGS.upd_site_devs))

		elif ARGS.upd_site_vlans or ARGS.upd_site_vlans_desc:
			if ARGS.upd_site_vlans:
				site_list = ARGS.upd_site_vlans.split(',')
			else:
				site_list = ARGS.upd_site_vlans_desc.split(',')
			for site in site_list:
				if NETBOX_API.dcim.sites.get(name=site) or NETBOX_API.dcim.sites.get(name=site.upper()) \
					or NETBOX_API.dcim.sites.get(name=site.lower()):
					dev_list = NETBOX_API.dcim.devices.filter(site=site.lower())
					if ARGS.upd_site_vlans:
						update_device_vlans(devices=dev_list)
					else:
						update_device_vlans_desc(devices=dev_list)
				else:
					raise Exception('Site \'{}\' not found!'.format(ARGS.upd_site_vlans))

		elif ARGS.upd_db_dev:
			update_netbox_db(device=ARGS.upd_db_dev)

		elif ARGS.site_circuits:
			if ARGS.site_circuits != 'all':
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
