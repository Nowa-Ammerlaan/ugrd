__version__ = '0.7.1'
__author__ = 'desultory'

from ugrd.fs.mounts import _get_mount_source


def _process_root_subvol(self, root_subvol: str) -> None:
    """ processes the root subvolume, masks the mount_root function. """
    self.update({'root_subvol': root_subvol})
    self.logger.debug("Set root_subvol to: %s", root_subvol)
    self['masks'] = {'init_mount': 'mount_root'}


def _process_subvol_selector(self, subvol_selector: bool) -> None:
    """
    Processes the subvol selector parameter
    Adds the base_mount_paths to paths if enabled.
    Masks the mount_root function if enabled.
    """
    if subvol_selector:
        self.update({'subvol_selector': subvol_selector})
        self.logger.debug("Set subvol_selector to: %s", subvol_selector)
        self['paths'] = self['base_mount_path']
        self['masks'] = {'init_mount': 'mount_root'}


def btrfs_scan(self) -> str:
    """ scan for new btrfs devices. """
    return "btrfs device scan"


def select_subvol(self) -> str:
    """ Returns a bash script to list subvolumes on the root volume. """
    if not self.get('subvol_selector'):
        self.logger.log(5, "subvol_selector not set, skipping")
        return

    root_volume = self['mounts']['root']['destination']
    out = [f'if [ -z "$(btrfs subvolume list -o {root_volume})" ]; then',
           f"    echo 'Failed to list btrfs subvolumes for root volume: {root_volume}'",
           "else",
           "    echo 'Select a subvolume to use as root'",
           "    PS3='Subvolume: '",
           f"    select subvol in $(btrfs subvolume list -o {root_volume} " + "| awk '{print $9}'); do",
           "        case $subvol in",
           "            *)",
           "                if [[ -z $subvol ]]; then",
           "                    echo 'Invalid selection'",
           "                else",
           '                    echo "Selected subvolume: $subvol"',
           "                    export root_subvol=$subvol",
           "                    break",
           "                fi",
           "                ;;",
           "        esac",
           "    done",
           "fi"]
    return out


def mount_subvol(self) -> str:
    """ mounts a subvolume. """
    if not self.get('subvol_selector') and not self.get('root_subvol'):
        self.logger.log(5, "subvol_selector and root_subvol not set, skipping")
        return

    source = _get_mount_source(self, self['mounts']['root'])
    destination = self['mounts']['root']['destination'] if not self.get('switch_root_target') else self['switch_root_target']

    return f"mount -o subvol=$root_subvol {source} {destination}"


def set_root_subvol(self) -> str:
    """
    sets $root_subvol.
    Prefer root_subvol over subvol_selector.

    If the subvol selector is set, change the root_mount path to the base_mount_path.
    Set the switch_root_target to the original root_mount path.
    """
    if root_subvol := self.get('root_subvol'):
        return f"export root_subvol={root_subvol}"
    elif self.get('subvol_selector'):
        self.logger.info("Subvolume selector set, changing root_mount path to: %s", self['base_mount_path'])
        self['switch_root_target'] = self['mounts']['root']['destination']
        self['mounts'] = {'root': {'destination': self['base_mount_path']}}

