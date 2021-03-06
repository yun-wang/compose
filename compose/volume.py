from __future__ import absolute_import
from __future__ import unicode_literals

import logging

from docker.errors import APIError
from docker.errors import NotFound

from .config import ConfigurationError

log = logging.getLogger(__name__)


class Volume(object):
    def __init__(self, client, project, name, driver=None, driver_opts=None,
                 external_name=None):
        self.client = client
        self.project = project
        self.name = name
        self.driver = driver
        self.driver_opts = driver_opts
        self.external_name = external_name

    def create(self):
        return self.client.create_volume(
            self.full_name, self.driver, self.driver_opts
        )

    def remove(self):
        if self.external:
            log.info("Volume %s is external, skipping", self.full_name)
            return
        log.info("Removing volume %s", self.full_name)
        return self.client.remove_volume(self.full_name)

    def inspect(self):
        return self.client.inspect_volume(self.full_name)

    def exists(self):
        try:
            self.inspect()
        except NotFound:
            return False
        return True

    @property
    def external(self):
        return bool(self.external_name)

    @property
    def full_name(self):
        if self.external_name:
            return self.external_name
        return '{0}_{1}'.format(self.project, self.name)


class ProjectVolumes(object):

    def __init__(self, volumes):
        self.volumes = volumes

    @classmethod
    def from_config(cls, name, config_data, client):
        config_volumes = config_data.volumes or {}
        volumes = {
            vol_name: Volume(
                client=client,
                project=name,
                name=vol_name,
                driver=data.get('driver'),
                driver_opts=data.get('driver_opts'),
                external_name=data.get('external_name')
            )
            for vol_name, data in config_volumes.items()
        }
        return cls(volumes)

    def remove(self):
        for volume in self.volumes.values():
            volume.remove()

    def initialize(self):
        try:
            for volume in self.volumes.values():
                if volume.external:
                    log.debug(
                        'Volume {0} declared as external. No new '
                        'volume will be created.'.format(volume.name)
                    )
                    if not volume.exists():
                        raise ConfigurationError(
                            'Volume {name} declared as external, but could'
                            ' not be found. Please create the volume manually'
                            ' using `{command}{name}` and try again.'.format(
                                name=volume.full_name,
                                command='docker volume create --name='
                            )
                        )
                    continue
                log.info(
                    'Creating volume "{0}" with {1} driver'.format(
                        volume.full_name, volume.driver or 'default'
                    )
                )
                volume.create()
        except NotFound:
            raise ConfigurationError(
                'Volume %s specifies nonexistent driver %s' % (volume.name, volume.driver)
            )
        except APIError as e:
            if 'Choose a different volume name' in str(e):
                raise ConfigurationError(
                    'Configuration for volume {0} specifies driver {1}, but '
                    'a volume with the same name uses a different driver '
                    '({3}). If you wish to use the new configuration, please '
                    'remove the existing volume "{2}" first:\n'
                    '$ docker volume rm {2}'.format(
                        volume.name, volume.driver, volume.full_name,
                        volume.inspect()['Driver']
                    )
                )

    def namespace_spec(self, volume_spec):
        if not volume_spec.is_named_volume:
            return volume_spec

        volume = self.volumes[volume_spec.external]
        return volume_spec._replace(external=volume.full_name)
