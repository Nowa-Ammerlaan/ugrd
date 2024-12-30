__author__ = "desultory"
__version__ = "3.10.0"

from pathlib import Path

from ugrd import AutodetectError, ValidationError
from zenlib.util import colorize, contains, unset

_module_name = "ugrd.crypto.cryptsetup"


CRYPTSETUP_KEY_PARAMETERS = ["key_command", "plymouth_key_command", "reset_command"]
CRYPTSETUP_PARAMETERS = [
    "key_type",
    "partuuid",
    "uuid",
    "path",
    "key_file",
    "header_file",
    "retries",
    *CRYPTSETUP_KEY_PARAMETERS,
    "try_nokey",
    "include_key",
    "include_header",
    "validate_key",
    "validate_header",
]


def _merge_cryptsetup(self, mapped_name: str, config: dict) -> None:
    """Merges the cryptsetup configuration"""
    if mapped_name not in self["cryptsetup"]:
        return config

    self.logger.log(5, "Existing cryptsetup configuration: %s" % self["cryptsetup"][mapped_name])
    self.logger.debug("[%s] Merging cryptsetup configuration: %s" % (mapped_name, config))
    return dict(self["cryptsetup"][mapped_name], **config)


def _process_cryptsetup_key_types_multi(self, key_type: str, config: dict) -> None:
    """Processes the cryptsetup key types.
    Updates the key type configuration if it already exists, otherwise creates a new key type."""
    self.logger.debug("[%s] Processing cryptsetup key type configuration: %s" % (key_type, config))
    for parameter in config:
        if parameter not in CRYPTSETUP_KEY_PARAMETERS:
            raise ValueError("Invalid parameter: %s" % parameter)

    # Update the key if it already exists, otherwise create a new key type
    if key_type in self["cryptsetup_key_types"]:
        self.logger.debug("[%s] Updating key type configuration: %s" % (key_type, config))
        self["cryptsetup_key_types"][key_type].update(config)
    else:
        # Make sure the key type has a key command
        if "key_command" not in config:
            raise ValidationError("Missing key_command for key type: %s" % key_type)
        self["cryptsetup_key_types"][key_type] = config


@contains("validate", "Skipping cryptsetup keyfile validation.", log_level=30)
def _validate_crypysetup_key(self, key_parameters: dict) -> None:
    """Validates the cryptsetup key"""
    if key_parameters.get("include_key"):
        return self.logger.info("Skipping key validation for included key.")
    elif key_parameters.get("validate_key") is False:
        return self.logger.info("Skipping key validation for: %s" % colorize(key_parameters["key_file"], "yellow"))

    key_path = Path(key_parameters["key_file"])

    if self["cryptsetup_keyfile_validation"] and key_parameters.get("validate_key") is not False:
        if not key_path.exists():  # Do a preliminary check to see if the key file exists
            raise FileNotFoundError("Key file not found: %s" % key_path)
        self["check_included_or_mounted"] = key_path  # Add a proper check for later


@contains("validate", "Skipping cryptsetup configuration validation.", log_level=30)
def _validate_cryptsetup_config(self, mapped_name: str) -> None:
    try:
        config = self["cryptsetup"][mapped_name]
    except KeyError:
        raise KeyError("No cryptsetup configuration found for: %s" % mapped_name)
    self.logger.log(5, "[%s] Validating cryptsetup configuration: %s" % (mapped_name, config))
    for parameter in config:
        if parameter not in CRYPTSETUP_PARAMETERS:
            raise ValueError("Invalid parameter: %s" % parameter)

    if config.get("header_file"):  # Check that he header is defined with a partuuid or path
        if not config.get("partuuid") and not config.get("path"):
            self.logger.warning(
                "A partuuid or device path must be specified when using detached headers: %s" % mapped_name
            )
            if config.get("uuid"):
                raise ValueError("A UUID cannot be used with a detached header: %s" % mapped_name)
        if not Path(
            config["header_file"]
        ).exists():  # Make sure the header file exists, it may not be present at build time
            self.logger.warning(
                "[%s] Header file not found: %s" % (mapped_name, colorize(config["header_file"], "yellow"))
            )
    elif not any([config.get("partuuid"), config.get("uuid"), config.get("path")]):
        if not self["autodetect_root_luks"]:
            raise ValidationError(
                "A device uuid, partuuid, or path must be specified for cryptsetup mount: %s" % mapped_name
            )

    if config.get("key_file"):
        _validate_crypysetup_key(self, config)


def _process_cryptsetup_multi(self, mapped_name: str, config: dict) -> None:
    """Processes the cryptsetup configuration"""
    for parameter in config:
        if parameter not in CRYPTSETUP_PARAMETERS:
            self.logger.error("[%s] Unknown parameter: %s" % (mapped_name, colorize(parameter, "red", bold=True)))

    config = _merge_cryptsetup(self, mapped_name, config)  # Merge the config with the existing configuration
    self.logger.debug("[%s] Processing cryptsetup configuration: %s" % (mapped_name, config))
    # Check if the key type is defined in the configuration, otherwise use the default, check if it's valid
    if key_type := config.get("key_type", self.get("cryptsetup_key_type")):
        self.logger.debug("[%s] Using key type: %s" % (mapped_name, key_type))
        if key_type not in self["cryptsetup_key_types"]:
            raise ValueError("Unknown key type: %s" % key_type)
        config["key_type"] = key_type

        # Inherit from the key type configuration
        for parameter in CRYPTSETUP_KEY_PARAMETERS:
            if value := self["cryptsetup_key_types"][key_type].get(parameter):
                config[parameter] = value.format(**config)

    # Include the key file or header if set
    for file_type in ["key", "header"]:
        if config.get(f"include_{file_type}"):
            self["dependencies"] = config[f"{file_type}_file"]

    if not config.get("retries"):
        self.logger.info(
            "[%s:%s] No retries specified, using default: %s" % (_module_name, mapped_name, self["cryptsetup_retries"])
        )
        config["retries"] = self["cryptsetup_retries"]

    self["cryptsetup"][mapped_name] = config


def _get_dm_info(self, mapped_name: str) -> dict:
    """Gets the device mapper information for a particular device."""
    for device_info in self["_vblk_info"].values():
        if device_info["name"] == mapped_name:
            return device_info
    raise AutodetectError("No device mapper information found for: %s" % mapped_name)


def _get_dm_slave_info(self, device_info: dict) -> (str, dict):
    """Gets the device mapper slave information for a particular device."""
    slave_source = device_info["slaves"][0]
    try:
        slave_device = f"/dev/{slave_source}"
        return slave_device, self["_blkid_info"][slave_device]
    except KeyError:
        slave_device = f"/dev/mapper/{slave_source}"
        return slave_device, self["_blkid_info"][slave_device]


def _read_cryptsetup_header(self, mapped_name: str, slave_device: str = None) -> dict:
    """Reads LUKS header information from a device or header file into a dict"""
    from json import loads

    header_file = self["cryptsetup"][mapped_name].get("header_file")
    if not header_file:
        if slave_device:
            header_file = slave_device
        else:
            slave_device, _ = _get_dm_slave_info(self, _get_dm_info(self, mapped_name))
            header_file = slave_device
    try:  # Try to read the header, return data, decoded and loaded, as a dictionary
        luks_info = loads(
            self._run(
                ["cryptsetup", "luksDump", "--dump-json-metadata", header_file], fail_silent=True, fail_hard=True
            ).stdout.decode()
        )
        self.logger.debug("[%s] LUKS header information: %s" % (mapped_name, luks_info))
        raw_luks_info = self._run(["cryptsetup", "luksDump", "--debug", header_file]).stdout.decode().split("\n")
        # --dump-json-metadata does not include the UUID, so we need to parse it from the raw output
        for line in raw_luks_info:
            if "UUID" in line:
                luks_info["uuid"] = line.split()[1]
                break
        return luks_info
    except RuntimeError as e:
        if not self["cryptsetup"][mapped_name].get("header_file"):
            self.logger.error("Unable to read LUKS header: %s" % colorize(e, "red", bold=True, bright=True))
        else:
            self.logger.warning("Cannot read detached LUKS header for validation: %s" % colorize(e, "yellow"))
    return {}


def _detect_luks_aes_module(self, luks_cipher_name: str) -> None:
    """Using the cipher name from the LUKS header, detects the corresponding kernel module."""
    aes_type = luks_cipher_name.split("-")[1]  # Get the cipher type from the name
    self["_kmod_auto"] = aes_type  # Add the aes type to the kernel modules

    crypto_name = f"{aes_type}(aes)"  # Format the name like the /proc/crypto entry
    crypto_config = self["_crypto_ciphers"][crypto_name]
    if crypto_config["module"] == "kernel":
        self.logger.debug("Cipher kernel modules are builtin: %s" % crypto_name)
    else:
        self.logger.info(
            "[%s] Adding kernel module for LUKS cipher: %s" % (crypto_name, colorize(crypto_config["module"], "cyan"))
        )
        self["_kmod_auto"] = crypto_config["module"]


def _detect_luks_header_aes(self, luks_info: dict) -> dict:
    """Checks the cipher type in the LUKS header, reads /proc/crypto to find the
    corresponding driver. If it's not builtin, adds the module to the kernel modules."""
    for keyslot in luks_info.get("keyslots", {}).values():
        if keyslot.get("area", {}).get("encryption", "").startswith("aes"):
            _detect_luks_aes_module(self, keyslot["area"]["encryption"])
    for segment in luks_info.get("segments", {}).values():
        if segment.get("encryption", "").startswith("aes"):
            _detect_luks_aes_module(self, segment["encryption"])


def _detect_luks_header_sha(self, luks_info: dict) -> dict:
    """Reads the hash algorithm from the LUKS header,
    enables the corresponding kernel module using _crypto_ciphers"""
    for keyslot in luks_info.get("keyslots", {}).values():
        if keyslot.get("af", {}).get("hash", "").startswith("sha"):
            self["kernel_modules"] = self._crypto_ciphers[keyslot["af"]["hash"]]["driver"]
    for digest in luks_info.get("digests", {}).values():
        if digest.get("hash", "").startswith("sha"):
            self["kernel_modules"] = self._crypto_ciphers[digest["hash"]]["driver"]


@contains("cryptsetup_header_validation", "Skipping cryptsetup header validation.", log_level=30)
def _validate_cryptsetup_header(self, mapped_name: str) -> None:
    """Validates configured cryptsetup volumes against the LUKS header."""
    cryptsetup_info = self["cryptsetup"][mapped_name]
    if cryptsetup_info.get("validate_header") is False:
        return self.logger.warning("Skipping cryptsetup header validation for: %s" % colorize(mapped_name, "yellow"))

    luks_info = _read_cryptsetup_header(self, mapped_name)
    if not luks_info:
        raise ValidationError("[%s] Unable to read LUKS header." % mapped_name)

    if uuid := cryptsetup_info.get("uuid"):
        if luks_info.get("uuid") != uuid:
            raise ValidationError(
                "[%s] LUKS UUID mismatch, found '%s', expected: %s" % (mapped_name, luks_info["uuid"], uuid)
            )

    _detect_luks_header_aes(self, luks_info)
    _detect_luks_header_sha(self, luks_info)

    if not self["argon2"]:  # if argon support was not detected, check if the header wants it
        for keyslot in luks_info.get("keyslots", {}).values():
            if keyslot.get("kdf", {}).get("type") == "argon2id":
                raise ValidationError("[%s] Missing cryptsetup dependency: libargon2.so" % mapped_name)

    if "header_file" in cryptsetup_info:
        self["check_included_or_mounted"] = cryptsetup_info["header_file"]  # Add the header file to the check list


@contains("hostonly", "Skipping cryptsetup device check.", log_level=30)
def _validate_cryptsetup_device(self, mapped_name) -> None:
    """Validates a cryptsetup device against the device mapper information,
    blkid information, and cryptsetup information.
    Uses `cryptsetup luksDump` to check that the device is a LUKS device."""
    dm_info = _get_dm_info(self, mapped_name)

    if not dm_info["uuid"].startswith("CRYPT-LUKS"):  # Ensure the device is a crypt device
        raise ValueError("Device is not a crypt device: %s" % dm_info)

    cryptsetup_info = self["cryptsetup"][mapped_name]  # Get the cryptsetup information
    if cryptsetup_info.get("validate") is False:
        return self.logger.warning("Skipping cryptsetup device validation: %s" % colorize(mapped_name, "yellow"))

    slave_device, blkid_info = _get_dm_slave_info(self, dm_info)  # Get the blkid information

    for token_type in ["partuuid", "uuid"]:  # Validate the uuid/partuuid token against blkid info
        if cryptsetup_token := cryptsetup_info.get(token_type):
            if blkid_info.get(token_type) != cryptsetup_token:
                raise ValidationError(
                    "[%s] LUKS %s mismatch, found '%s', expected: %s"
                    % (mapped_name, token_type, cryptsetup_token, blkid_info[token_type])
                )
            break
    else:
        raise ValueError("[%s] No UUID or PARTUUID set for LUKS source: %s" % (mapped_name, cryptsetup_info))

    _validate_cryptsetup_header(self, mapped_name)  # Run header validation, mostly for crypto modules


@unset("_cryptsetup_backend")
def detect_cryptsetup_backend(self) -> None:
    """Determines the cryptsetup backend by running 'cryptsetup --debug luksDump' on this file"""
    from re import search

    try:
        raw_luks_info = (
            self._run(["cryptsetup", "--debug", "luksDump", __file__], fail_silent=True, fail_hard=False)
            .stdout.decode()
            .split("\n")
        )
        for line in raw_luks_info:
            if line.startswith("# Crypto backend"):
                backend = search(r"backend \((.+)\)", line).group(1)
                self["_cryptsetup_backend"] = backend.split()[0].lower()
                return self.logger.info(
                    "Detected cryptsetup backend: %s" % colorize(self["_cryptsetup_backend"], "cyan")
                )
    except RuntimeError as e:
        self.logger.error("Unable to determine cryptsetup backend: %s" % e)


def _get_openssl_kdfs(self) -> list[str]:
    """Gets the available KDFs from OpenSSL"""
    kdfs = self._run(["openssl", "list", "-kdf-algorithms"]).stdout.decode().lower().split("\n")
    self.logger.debug("OpenSSL KDFs: %s" % kdfs)
    return kdfs


@unset("argon2")
def detect_argon2(self) -> None:
    """Validates that argon2 is available when argon2id is used."""
    from ugrd.base.core import calculate_dependencies

    cryptsetup_deps = calculate_dependencies(self, "cryptsetup")

    match self["_cryptsetup_backend"]:
        case "openssl":
            openssl_kdfs = _get_openssl_kdfs(self)
            self["argon2"] = any(kdf.lstrip().startswith("argon2id") and "default" in kdf for kdf in openssl_kdfs)
            if not any(dep.name.startswith("libcrypto.so") for dep in cryptsetup_deps):
                self.logger.error("Cryptsetup is linked against OpenSSL, but libcrypto.so is not in dependencies.")
        case "gcrypt":
            gcrypt_version = self._run(["libgcrypt-config", "--version"]).stdout.decode().strip().split("-")[0]
            maj, minor, patch = map(int, gcrypt_version.split("."))
            if not any(dep.name.startswith("libgcrypt.so") for dep in cryptsetup_deps):
                self.logger.error("Cryptsetup is linked against Libgcrypt, but libgcrypt.so is not in dependencies.")
            if (maj, minor, patch) >= (1, 11, 0):
                self["argon2"] = True
            else:
                self.logger.error("Gcrypt version %s may not support argon2id." % gcrypt_version)
        case _:
            self.logger.error("Unable to determine cryptsetup backend.")

    libargon2 = any(dep.name.startswith("libargon2.so") for dep in cryptsetup_deps)
    if libargon2:
        self["argon2"] = True

    if not self["argon2"]:
        self.logger.error("Cryptsetup is not linked against libargon2.")


@contains("hostonly")
def detect_ciphers(self) -> None:
    """Populates _crypto_ciphers using /proc/crypto"""

    def get_value(line):
        return line.split(":")[1].strip()

    with open("/proc/crypto") as crypto_file:
        current_name = None
        for line in crypto_file:
            if line.startswith("name"):
                current_name = get_value(line)
                self._crypto_ciphers[current_name] = {}
            elif not current_name:
                continue  # Skip lines until a name is found
            elif line.startswith("driver"):
                self._crypto_ciphers[current_name]["driver"] = get_value(line)
            elif line.startswith("module"):
                self._crypto_ciphers[current_name]["module"] = get_value(line)


@contains("validate", "Skipping cryptsetup configuration validation.", log_level=30)
def _validate_luks_config(self, mapped_name: str) -> None:
    """Checks that a LUKS config portion is valid."""
    _validate_cryptsetup_device(self, mapped_name)
    _validate_cryptsetup_config(self, mapped_name)


def export_crypt_sources(self) -> list[str]:
    """Validates the cryptsetup configuration (if enabled).
    Adds the cryptsetup source and token to the exports.
    Sets the token to the partuuid or uuid if it exists.
    Sets the SOURCE when using a path.
    Only allows using the path if validation is disabled."""
    for name, parameters in self["cryptsetup"].items():
        _validate_luks_config(self, name)
        if parameters.get("path"):
            if not self["validate"]:
                self.logger.warning(
                    "Using device paths is unreliable and can result in boot failures. Consider using partuuid."
                )
                self["exports"]["CRYPTSETUP_SOURCE_%s" % name] = parameters["path"]
                self.logger.info("Set CRYPTSETUP_SOURCE_%s: %s" % (name, parameters.get("path")))
                continue
            raise ValidationError("Validation must be disabled to use device paths with the cryptsetup module.")
        elif not parameters.get("partuuid") and not parameters.get("uuid") and parameters.get("path"):
            raise ValidationError("Device source for cryptsetup mount must be specified: %s" % name)

        for token_type in ["partuuid", "uuid"]:
            if token := parameters.get(token_type):
                self["exports"]["CRYPTSETUP_TOKEN_%s" % name] = f"{token_type.upper()}={token}"
                self.logger.debug("Set CRYPTSETUP_TOKEN_%s: %s=%s" % (name, token_type.upper(), token))
                break
        else:
            raise ValidationError("A partuuid or uuid must be specified for cryptsetup mount: %s" % name)


def get_crypt_dev(self) -> list[str]:
    """Gets the device path for a particular cryptsetup device at runtime.
    First attempts to read CRYPTSETUP_SOURCE_{name} if it exists.
    If it doesn't exist, or the device is not found, it will attempt to resolve the device using the token.
    If that doesn't exist, it will fail."""
    return [
        'source_dev="$(readvar CRYPTSETUP_SOURCE_"$1")"',
        'source_token="$(readvar CRYPTSETUP_TOKEN_"$1")"',
        'if [ -n "$source_dev" ]; then',
        '    if [ -e "$source_dev" ]; then',
        '        echo -n "$source_dev"',
        "        return",
        "    fi",
        "fi",
        'if [ -n "$source_token" ]; then',
        '    source_dev=$(blkid --match-token "$source_token" --output device)',
        '    if [ -n "$source_dev" ]; then',
        '        echo -n "$source_dev"',
        "    fi",
        "fi",
    ]


def open_crypt_device(self, name: str, parameters: dict) -> list[str]:
    """Returns a bash script to open a cryptsetup device."""
    self.logger.debug("[%s] Processing cryptsetup volume: %s" % (name, parameters))
    retries = parameters["retries"]

    out = [f"prompt_user 'Press enter to unlock device: {name}'"] if self["cryptsetup_prompt"] else []
    out += [f"for ((i = 1; i <= {retries}; i++)); do"]

    # Resolve the device source using get_crypt_dev, if no source is returned, run rd_fail
    out += [
        f'    crypt_dev="$(get_crypt_dev {name})"',
        '    if [ -z "$crypt_dev" ]; then',
        f'        rd_fail "Failed to resolve device source for cryptsetup mount: {name}"',
        "    fi",
    ]

    reset_command = parameters.get("reset_command", "continue")
    # When there is a key command, evaluate it into $key_data
    if "key_command" in parameters:
        self.logger.debug("[%s] Using key command: %s" % (name, parameters["key_command"]))
        out += [
            f"    einfo 'Attempting to open LUKS key: {parameters['key_file']}'",
            f"    edebug 'Using key command: {parameters['key_command']}'",
        ]

        if "plymouth_key_command" in parameters and "ugrd.base.plymouth" in self["modules"]:
            out += [
                "    if plymouth --ping; then",
                f'        plymouth ask-for-password --prompt "[${{i}} / {retries}] Enter passphrase to unlock key for: {name}" --command "{parameters["plymouth_key_command"]}" --number-of-tries 1 > /run/vars/key_data || {reset_command}',
                "    else",
                f'        {parameters["key_command"]} > /run/vars/key_data || {reset_command}',
                "    fi",
            ]
        else:
            out += [f"    {parameters['key_command']} > /run/vars/key_data || {reset_command}"]

    cryptsetup_command = "cryptsetup open --tries 1"  # Set tries to 1 since it runs in the loop
    cryptsetup_target = f'"$crypt_dev" {name}'  # Add a variable for the source device and mapped name

    if header_file := parameters.get("header_file"):  # Use the header file if it exists
        out += [f"    einfo 'Using header file: {header_file}'"]
        cryptsetup_command += f" --header {header_file}"

    if self["cryptsetup_trim"]:
        cryptsetup_command += " --allow-discards"
        self.logger.warning("Using --allow-discards can be a security risk.")

    # Check if the device was successfully opened
    out += [
        '    einfo "Unlocking device: $crypt_dev"',  # Unlock using key data if it exists
        "    if [ -e /run/vars/key_data ]; then",
        f"        if {cryptsetup_command} --key-file=/run/vars/key_data {cryptsetup_target}; then",
        "            rm /run/vars/key_data",  # Remove the key data file
        "            break",
        "        fi",  # Try to open the device using plymouth if it's running
        "        rm /run/vars/key_data",  # Remove the key data file
    ]
    if "ugrd.base.plymouth" in self["modules"]:  # Attempt plain unlock if using plymouth
        out += [
            f'    elif plymouth --ping && plymouth ask-for-password --prompt "[${{i}} / {retries}] Enter passphrase to unlock {name}" --command "{cryptsetup_command} {cryptsetup_target}" --number-of-tries 1; then',
            "        break",
        ]  # Break if the device was successfully opened
    if "key_file" in parameters:  # try a key file directly if it exists
        out += [f'    elif {cryptsetup_command} --key-file {parameters["key_file"]} {cryptsetup_target}; then']
    else:  # Otherwise, open directly
        out += [f"    elif {cryptsetup_command} {cryptsetup_target}; then"]
    out += ["        break", "    fi", f'    ewarn "Failed to open device: {name} ($i / {retries})"']
    # Halt if the autoretry is disabled
    if not self["cryptsetup_autoretry"]:
        out += ['    prompt_user "Press enter to retry"']
    # Add the reset command if it exists
    if reset_command != "continue":
        out += ['    einfo "Running key reset command"', f"    {reset_command}"]
    out += ["done\n"]

    return out


def crypt_init(self) -> list[str]:
    """Generates the bash script portion to prompt for keys."""
    if self["loglevel"] > 5:
        self.logger.warning("loglevel > 5, cryptsetup prompts may not be visible.")

    out = [r'einfo "Unlocking LUKS volumes, ugrd.cryptsetup version: %s"' % __version__]
    for name, parameters in self["cryptsetup"].items():
        # Check if the volume is already open, if so, skip it
        out += [
            f"if cryptsetup status {name} > /dev/null 2>&1; then",
            f'    ewarn "Device already open: {name}"',
            "    return",
            "fi",
        ]
        out += open_crypt_device(self, name, parameters)
        if "try_nokey" in parameters and parameters.get("key_file"):
            new_params = parameters.copy()
            for parameter in ["key_file", "key_command", "reset_command"]:
                try:
                    new_params.pop(parameter)
                except KeyError:
                    pass
            out += [
                f"if ! cryptsetup status {name} > /dev/null 2>&1; then",
                f'    ewarn "Failed to open device using keys: {name}"',
            ]
            out += [f"    {bash_line}" for bash_line in open_crypt_device(self, name, new_params)]
            out += ["fi"]
        # Check that the device was successfully opened
        out += [
            f"if ! cryptsetup status {name} > /dev/null 2>&1; then",
            f'    rd_fail "Failed to open cryptsetup device: {name}"',
            "fi",
            f'einfo "Successfully opened cryptsetup device: {name}"',
        ]
    return out
