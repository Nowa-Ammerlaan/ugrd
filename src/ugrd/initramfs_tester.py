# Tests the initramfs image

from zenlib.logging import loggify
from ugrd.initramfs_generator import InitramfsGenerator


@loggify
class InitramfsTester:
    def __init__(self, initrd_generator, test_dir="./test_fs", *args, **kwargs):
        self.initrd_generator = initrd_generator

        self.target_fs = InitramfsGenerator(logger=self.logger, build_dir=test_dir, config=None, modules='ugrd.fs.test_image', NO_BASE=True, out_dir=initrd_generator.out_dir, out_file='ugrd-test-rootfs')

    def test(self):
        self.target_fs.build()
        self.logger.info("Testing initramfs image: %s", self.initrd_generator['_archive_out_path'])





