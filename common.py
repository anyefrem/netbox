import os
import sys
import yaml
import pynetbox

if os.path.exists('./config.yml'):
	with open('./config.yml') as f:
		YAML_PARAMS = yaml.safe_load(f)
	f.close()
else:
	print('config.yml not found!')
	sys.exit(1)

NETBOX_URL = YAML_PARAMS['netbox']['url']
NETBOX_TOKEN = YAML_PARAMS['netbox']['token']
NETBOX_API = pynetbox.api(NETBOX_URL, token=NETBOX_TOKEN)
LLDP_INCOMPATIBLE_SLUGS = YAML_PARAMS['lldp_incompatible_slugs']
