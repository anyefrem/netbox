#!/usr/bin/env python
import sys
import os
import subprocess
from jinja2 import Environment, FileSystemLoader


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
