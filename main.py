#!/usr/bin/env python

from initramfs_generator import InitramfsGenerator

from argparse import ArgumentParser
import logging


if __name__ == '__main__':
    argparser = ArgumentParser(prog='custom-initramfs',
                               description='Initramfs generator')

    argparser.add_argument('config_file',
                           action='store',
                           nargs='?',
                           help='Config file location')

    args = argparser.parse_args()

    logger = logging.getLogger()
    logger.setLevel(10)

    kwargs = {'logger': logger}
    if config := args.config_file:
        kwargs['config'] = config

    generator = InitramfsGenerator(**kwargs)

    try:
        generator.build_structure()
        generator.generate_init()
    except Exception as e:
        logger.error("\n\nError: %s\n\n" % e)
        logger.info("Dumping config dict:\n")
        print(generator.config_dict)
