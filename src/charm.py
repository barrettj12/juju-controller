#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# Licensed under the GPLv3, see LICENSE file for details.

import logging
import os
import yaml

from charmhelpers.core import hookenv
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus
from ops.framework import StoredState

logger = logging.getLogger(__name__)


class JujuControllerCharm(CharmBase):
    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(
            self.on.dashboard_relation_joined, self._on_dashboard_relation_joined)
        self.framework.observe(
            self.on.website_relation_joined, self._on_website_relation_joined)
        self.framework.observe(
            self.on.metrics_endpoint_relation_created, self._on_metrics_endpoint_relation_created)

    def _on_start(self, _):
        self.unit.status = ActiveStatus()

    def _on_config_changed(self, _):
        controller_url = self.config["controller-url"]
        logger.info("got a new controller-url: %r", controller_url)

    def _on_dashboard_relation_joined(self, event):
        logger.info("got a new dashboard relation: %r", event)

        event.relation.data[self.app].update({
            'controller-url': self.config['controller-url'],
            'identity-provider-url': self.config['identity-provider-url'],
            'is-juju': str(self.config['is-juju']),
        })

        # TODO: do we need to poke something on the controller so that the `juju
        # dashboard` command will work?

    def _on_website_relation_joined(self, event):
        """Connect a website relation."""
        logger.info("got a new website relation: %r", event)
        port = api_port()
        if port is None:
            logger.error("machine does not appear to be a controller")
            self.unit.status = BlockedStatus('machine does not appear to be a controller')
            return

        ingress_address = hookenv.ingress_address(event.relation.id, hookenv.local_unit())

        event.relation.data[self.unit].update({
            'hostname': ingress_address,
            'private-address': ingress_address,
            'port': str(port)
        })

    def _on_metrics_endpoint_relation_created(self, event):
        logger.info("Prometheus relation created: %r", event)
        self.metrics_endpoint = MetricsEndpointProvider(self, jobs = [
            {
                "job_name": "juju",
                "metrics_path": "/introspection/metrics",
                "static_configs": [
                    {
                        "targets": ["*:17070"]
                    }
                ],
                #### These settings not allowed by library
                "scheme": "https",
                "basic_auth": {
                    "username": "user-prometheus",
                    "password": "1234"
                },
                "tls_config": {
                    "ca_file": self.config["ca-cert"],
                },
            }
        ])


def api_port():
    ''' api_port determines the port that the controller's API server is
        listening on.  If the machine does not appear to be a juju
        controller then None is returned.
    '''
    machine = os.getenv('JUJU_MACHINE_ID')
    if machine is None:
        return None
    path = '/var/lib/juju/agents/machine-{}/agent.conf'.format(machine)
    with open(path) as f:
        params = yaml.safe_load(f)
    return params.get('apiport')


if __name__ == "__main__":
    main(JujuControllerCharm)
