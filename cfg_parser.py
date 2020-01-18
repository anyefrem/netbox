#!/usr/bin/env python


from ciscoconfparse import CiscoConfParse


def main():
	try:
		confparse = CiscoConfParse("example_config.txt")

	except Exception as e:
		msg = '\n\n\n*** Error in \'{0}___{1}\' function (line {2}): {3} ***\n\n\n'.format(
			os.path.basename(__file__), sys._getframe().f_code.co_name, sys.exc_info()[-1].tb_lineno, e)
		print(msg)
		sys.exit(1)

if __name__ == "__main__":
	main()
