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

    logging.getLogger().setLevel(20)

    kwargs = dict()
    if config := args.config_file:
        kwargs['config'] = config
    generator = InitramfsGenerator(**kwargs)
