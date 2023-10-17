# Initramfs generator

This project is a framework which can be used to generate an initramfs.

Executing `./main.py` will read the config from `config.toml` and use that to generate an initramfs.

The goal of the project was to design one that can be used to enter GPG keys for LUKS keyfiles over serial, to boot a btrfs raided filesystem.

## Usage

To use this script, configure `config.toml` to meet specifications and run `./main.py` as root.

> Example configs are available in the repo

### Passing a config file by name

Another config file can be used by passing it as an argument to `main.py`.

The example config can be used with `./main.py example_config.toml`

## Configuration

The main configuration file is `config.toml`

### Module config

#### base.base

Setting `out_dir` changes where the script writes the output files, it defaults to `initramfs` in the local dir.

Setting `clean` to `true` makes the script clean the output directory prior to generating it.

`shebang` is set by default, and sets the shebang on the init script.

`root_mount` takes a label or UUID for a volume to be mounted as the root filesystem.

`mounts.<mountname>` is defined with fstab details, such as `source`, `destination` and `type`.

`mount_wait` if set to true, waits for user input before attenmpting to mount the generated fstab at runtime, disabled by default. 

`mount_timeout` timeout for mount_wait to automatically continue.

#### base.kmod

This module is used to embed kernel modules into the initramfs. Both parameters are optional.
If the module is loaded, but configuration options are not passed, the generator will pull all currently running kernel modules from the active kernel.

`kernel_version` is used to specify the kernel version to pull modules for, should be a directory under `/lib/modules/<kernel_version>`.

`kernel_modules` is used to define a list of kernel module names to pull into the initramfs. If it is not set, all loaded kernel modules will be pulled.

`kmod_ignore` is used to specify kernel modules to ignore. If a module depends on one of these, it will throw an error and drop it from being included.

`kmod_init` is used to specify kernel modules to load at boot. If set, ONLY these modules will be loaded with modprobe. If unset, `kernel_modules` is used.

`_kmod_depend` is meant to be used within modules, specifies kernel modules which should be added to `kernel_modules` and `kmod_init`.

`kmod_ignore_softdeps` if set to true, ignores softdeps

#### crypto.gpg

This module is required to perform GPG decryption within the initramfs.

`gpg_public_key` is used to specify the location of a GPG public key to be added to the initramfs and imported into the keyring on start.
This should be defined globally and cen be used with a YubiKey.

#### crypto.cryptsetup

This module is used to decrypt LUKS volumes in the initramfs.

`cryptsetup` is a dictionary that contains the root devices to decrypt. `key_file` is optional within this dict, but `uuid` is required, ex:

```
[cryptsetup.root]
uuid = "9e04e825-7f60-4171-815a-86e01ec4c4d3"
```

`key_type` can be either `gpg` or `keyfile`. If it is not set, cryptsetup will prompt for a passphrase. If this is set globally, it applies to all `cryptsetup` definitions.

### General config

The following configuration options can exist in any module, or the base config

#### binaries

All entires specified in the `binaries` list will be imported into the initramfs.

`lddtree` is used to find the required libraries.

#### paths

All entries in the `paths` list will be created as folders under the `./initramfs` directory.

They should not start with a leading `/`

### modules

The modules config directive should contain a list with names specifying the path of which will be loaded, such as `base.base`, `base.serial` or `crypto.crypsetup`.

Another directory for modules can be created, the naming scheme is similar to how python imports work.

When a module is loaded, `initramfs_generator.py` will try to load a toml file for that module, parsing it in the same manner `config.yaml` is parsed.

The order in which modules/directives are loaded is very important!

### imports

The most powerful part of a module is the `imports` directive.

Imports are used to hook into the general processing scheme, and become part of the main `InitramfsGenerator` object.

Portions are loaded into the InitramfsGenerator's `config_dict` which is an `InitramfsConfigDict`

`imports` are defined like:

```
[imports.<hook>]
"module_dir.module_name" = [ "function_to_inject" ]
```

For example:

```
[imports.build_tasks]
"base.base" = [ "generate_fstab" ]
```

Is used in the base module to make the initramfs generator generate a fstab durinf the `build_tasks` phase.

Imported functions have access to the entire `self` scope, giving them full control of whatever other modules are loaded when they are executed, and the capability to dynamically create new functions.

This script should be executed as root, to have access to all files and libraries required to boot, so special care should be taken when loading and creating modules. 

#### config_processing

These imports are very special, they can be used to change how parameters are parsed by the internal `config_dict`.

A good example of this is in `base.py`:

```
def _process_mounts_multi(self, key, mount_config):
    """
    Processes the passed mounts into fstab mount objects
    under 'fstab_mounts'
    """
    if 'destination' not in mount_config:
        mount_config['destination'] = f"/{key}"  # prepend a slash

    try:
        self['mounts'][key] = FstabMount(**mount_config)
        self['paths'].append(mount_config['destination'])
    except ValueError as e:
        self.logger.error("Unable to process mount: %s" % key)
        self.logger.error(e)
```

This module manages mount management, and loads new mounts into fstab objects, also defined in the base module.

The name of `config_prcessing` functions is very important, it must be formatted like `_process_{name}` where the name is the root variable name in the yaml config.

If the function name has `_multi` at the end, it will be called using the `handle_plural` function, iterating over passed lists/dicts automatically.

A new root varaible named `oops` could be defined, and a function `_process_oops` could be created and imported, raising an error when this vlaue is found, for example.

This module is loaded in the imports section of the `base.yaml` file:

```
[imports.config_processing]
"base.base" = [ "_process_mounts_multi" ]
```

#### build_tasks

Build tasks are functions which will be executed after the directory structure has been generated using the specified `paths`.

The base module includes a build task for generating the fstab, which is activated with:

```
[imports.build_tasks]
"base.base" = [ "generate_fstab" ]
```

#### init hooks

By default, the specified init hooks are: `'init_pre', 'init_main', 'init_late', 'init_final'`

These hooks are defined under the `init_types` list in the `InitramfsGenerator` object.

When the init scripts are generated, functions under dicts in the config defined by the names in this list will be called to generate the init scripts.

This list can be updated to add or disable portions.  The order is important, as most internal hooks use `init_pre` and `init_final` to wrap every other init category, in order.

Each function should return a list of strings containing the shell lines, which will be written to the `init` file.

A general overview of the procedure used for generating the init is to write the chosen `shebang`, build in `init_pre`, then everything but `init_final`, then finally `init_final`.  These init portions are added to one file.

#### custom_init

To entirely change how the init files are generated, `custom_init` can be used. 

The `serial` module uses the `custom_init` hook to change the init creation procedure.

Like with the typical flow, it starts by creating the base `init` file with the shebang and `init_pre` portions. Once this is done, execution is handed off to all fucntions present in the `custom_init` imports.

Finally, like the standard init build, the `init_final` is written to the main `init` file.

```
[imports.custom_init]
"base.serial" = [ "custom_init" ]
```

The custom init works by creating an `init_main` file and returning a config line which will execute that file in a getty session.
This `init_main` file contains everything that would be in the standard init file, but without the `init_pre` and `init_final` portions. 


```
def custom_init(self):
    """
    init override
    """
    from os import chmod
    with open(f"{self.out_dir}/init_main.sh", 'w', encoding='utf-8') as main_init:
        main_init.write("#!/bin/bash\n")
        [main_init.write(f"{line}\n") for line in self.generate_init_main()]
    chmod(f"{self.out_dir}/init_main.sh", 0o755)
    return serial_init(self)


def serial_init(self):
    """
    start agetty
    """
    try:
        out = list()
        for name, config in self.config_dict['serial'].items():
            if config.get('local'):
                out.append(f"agetty --autologin root --login-program /init_main.sh -L {config['baud']} {name} {config['type']}")
            else:
                out.append(f"agetty --autologin root --login-program /init_main.sh {config['baud']} {name} {config['type']}")
        return out

```
