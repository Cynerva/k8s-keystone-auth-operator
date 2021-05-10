#!/usr/bin/env python3

import logging
from ops.charm import CharmBase
from ops.main import main

log = logging.getLogger()


class K8sKeystoneAuthCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.install, self.install)

    def install(self):
        print('install')


if __name__ == '__main__':
    main(K8sKeystoneAuthCharm)
